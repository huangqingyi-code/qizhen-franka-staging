# Linux Edge 安装文件

- **Connector 接入：按指南操作。** 安装、配对和配置后台服务通常不需要 Codex 参与开发。
- **Adapter 接入：使用现成包，或先开发再安装。** 没有适用的 Adapter 时，可借助 Codex 根据设备接口开发，再按第 4 章安装、启用并同步能力。

## 0. 在 Mac 或 Linux 上构建 wheel（设备端直接使用构建好的）

构建机器需要 Git 和可运行的 Docker。在仓库根目录执行：

```bash
git clone https://github.com/birdlet1982/Qizhen-Platform.git
cd Qizhen-Platform

mkdir -p dist/linux-edge

docker run --rm \
  -v "$PWD:/src:ro" \
  -v "$PWD/dist/linux-edge:/out" \
  python:3.12.13-slim-bookworm \
  python -m pip wheel --no-deps \
    --wheel-dir /out \
    /src/apps/linux-edge-runtime
```

如果已经有仓库，直接进入现有仓库根目录，无需再次克隆。即使在 Mac 上运行，上面的构建过程也发生在 Linux 容器中。

生成文件：

```text
dist/linux-edge/qizhen_linux_edge-0.1.0-py3-none-any.whl
```

在 Mac 上计算校验值：
```bash
shasum -a 256 dist/linux-edge/qizhen_linux_edge-0.1.0-py3-none-any.whl
```
在设备端上计算校验值：
```bash
sha256sum dist/linux-edge/qizhen_linux_edge-0.1.0-py3-none-any.whl
```

## 1. 准备 Python 3.12

Ubuntu / Debian，以目标普通用户执行：

```bash
sh install-python312.sh --install-deps --jobs 4
```

脚本内部仅通过 sudo 安装 apt 编译依赖，脚本本身不要加 sudo。依赖已准备好时可以省略 `--install-deps`；其他发行版先自行安装编译依赖，再运行不带该选项的命令。

脚本先检测 PATH 中的 `python3.12`、版本为 3.12 的 `python3`，以及之前准备好的独立解释器。找到模块完整的 Python 3.12 就直接复用，不读取源码包、不安装编译依赖；找不到或缺少必要模块时，自动校验同目录的源码包并编译安装到 `~/.local/opt/python-3.12.15`。若该目录已有不可用的安装，会保留它并改用新的 `python-3.12.15-rebuild-*` 目录。

需要编译时脚本会自动校验源码包。已有 Python 3.12 时，可以只运行 `sh install-python312.sh`，无需源码包或 `--install-deps`。两种成功路径都会创建 `~/.local/lib/qizhen-edge-installer`，不切换系统默认 Python。保留使用中的 Python 安装目录，虚拟环境依赖它。

## 2. 安装 Linux Edge

在传输过来的 `linux-edge` 目录内执行（当前目录需包含 `install.sh`、wheel 和对应的 `.sha256` 文件）：

```bash
(
  set -e

  wheel=qizhen_linux_edge-0.1.0-py3-none-any.whl
  sha256sum -c "$wheel.sha256"
  digest=$(awk 'NR == 1 {print $1}' "$wheel.sha256")

  sh install.sh "$wheel" "sha256:$digest"

  ~/.local/lib/qizhen-edge/current/bin/python --version
  ~/.local/bin/qizhen-linux-edge --version
  ~/.local/bin/qizhen-linux-edge doctor
)
```

apt 编译依赖和 wheel 运行依赖仍需要网络或提前准备的软件源。本目录不是完整的离线依赖包。

`install.sh` 会自动选择已准备好的 Python 3.12，并在安装后执行 `doctor`。脚本内部的 PATH 只对脚本生效。若当前终端尚不能识别命令，先执行 `export PATH="$HOME/.local/bin:$PATH"`，或使用完整路径 `~/.local/bin/qizhen-linux-edge`。

## 3. 配对并配置 Connector 服务

### 3.1 平台运行在本地 Mac：通过 SSH 隧道连接

当前 Mac 上的 Platform API 地址为 `http://127.0.0.1:18080`，网页入口为 `http://127.0.0.1:15173`。配对使用 Platform API 地址。

API 只绑定 Mac 的本地地址；设备端的 `127.0.0.1` 指向设备端自己，不能直接访问 Mac 的本地服务。客户端也要求非 localhost 地址使用 HTTPS，因此本地联调可以使用 SSH 隧道。

**在 Mac 上新开一个终端**，执行并保持运行：

```bash
ssh -p 18001 -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -R 127.0.0.1:18080:127.0.0.1:18080 \
  zhaoyunzyq@114.55.110.144
```

这会把设备端的本地 `18080` 端口转发到 Mac 的 Platform API。正常运行时，该命令可能没有输出，并会持续占用终端。

**在设备端上**验证平台连通性：

```bash
curl --fail --max-time 10 http://127.0.0.1:18080/readyz
```

确认返回 `"status":"ready"` 后，在设备端上发起配对：

```bash
qizhen-linux-edge pair \
  --url http://127.0.0.1:18080 \
  --name xxxx
```

配对命令会输出 `verification_code`（8 位核对码）。然后在 Mac 浏览器打开以下地址，将 `你的8位核对码` 替换为实际值：

```text
http://127.0.0.1:15173/open/provider/?pair=你的8位核对码#local-resource-pairing
```

登录后，在“确认这次接入请求”区域核对设备名称、操作系统和核对码，点击“确认由我接入”，再执行下方的“确认配对”。直接打开网页首页不会显示配对确认区。

如果忘记核对码，在设备端上执行 `qizhen-linux-edge pair-status` 查看。当前 CLI 返回的 `verification_url` 使用 API 端口及 `/open/` 路径；本地 Compose 请使用上面的网页端口 `15173` 和 `/open/provider/` 路径。若页面提示请求已过期，重新执行 `pair` 获取新的核对码。

使用这套连接方式时，Mac 上的 SSH 隧道需要一直运行，包括后续设备端的 systemd 后台服务运行期间。Mac 休眠、关闭隧道或连接中断后，需要重新建立隧道。

### 3.2 平台已有可访问的 HTTPS 地址

如果平台已提供目标 Linux 主机可访问的 HTTPS 地址，可直接在 Linux 主机上配对，无需上述 SSH 隧道。将平台地址和设备名称替换为实际值：

```bash
qizhen-linux-edge pair --url https://platform.example.edu --name lab-linux-edge
```

### 3.3 确认配对

完成任一种方式的配对请求，并在 Qizhen 中确认配对码后，在目标 Linux 主机上执行：

```bash
# 查询配对结果；网页确认后，会取得并保存设备凭据
# 成功后显示 status: paired，已配对时无需重复执行
qizhen-linux-edge pair-status --poll
qizhen-linux-edge status
```

### 3.4 先配置 systemd 用户服务（暂不启动）

以下命令在**目标 Linux 设备端**，以安装并配对 Connector 的同一个普通用户执行，不是在 Mac 或平台服务器上执行。目标系统需要支持 systemd 用户服务。

默认安装目录为 `~/.local/lib/qizhen-edge`，状态目录为 `~/.local/share/qizhen-edge`。在传输过来的 `linux-edge` 目录内执行，确保当前目录包含 `qizhen-linux-edge.service`：

```bash
~/.local/bin/qizhen-linux-edge doctor
~/.local/bin/qizhen-linux-edge status

mkdir -p ~/.config/systemd/user
cp qizhen-linux-edge.service ~/.config/systemd/user/
systemctl --user daemon-reload

# 设置用户服务管理器启动时自动运行，但此处暂不启动服务
systemctl --user enable qizhen-linux-edge.service

# 允许用户未登录时也运行用户服务，退出 SSH 后继续运行
# 仅此命令需要 sudo；不要用 sudo 执行 systemctl --user
sudo loginctl enable-linger "$USER"
```

`enable` 设置服务自动启动；`enable-linger` 让用户服务管理器无需登录也能在开机时运行。此处不使用 `--now`，先完成第 4.1 节的 Adapter 安装和能力同步，再启动服务。若服务原来已经运行，`enable` 不会将它停止；执行 Adapter 更新前仍应按更新步骤暂停接收请求。


常用管理命令：

```bash
# 重启服务
systemctl --user restart qizhen-linux-edge.service

# 停止服务，保留自动启动设置
systemctl --user stop qizhen-linux-edge.service

# 重新启动服务
systemctl --user start qizhen-linux-edge.service

# 查看最近 50 条日志
journalctl --user -u qizhen-linux-edge.service -n 50 --no-pager

# 实时查看日志；Ctrl+C 仅退出日志查看
journalctl --user -u qizhen-linux-edge.service -f

# 停用服务并取消自动启动
systemctl --user disable --now qizhen-linux-edge.service
```

## 4. Adapter 安装与后台运行

### 4.1 安装、启用并同步 Adapter

无论首次安装、增加自定义 Adapter，还是更新已有 Adapter，都先统一停止 Connector 后台服务，暂停接收平台任务。第 3.4 节已配置服务，因此首次安装时服务尚未运行也可以执行：

```bash
systemctl --user stop qizhen-linux-edge.service
```

若之前手动运行了 `qizhen-linux-edge run`，也须在原终端按 `Ctrl+C` 停止；`systemctl --user stop` 不会停止手动启动的前台进程。停止失败时先处理错误，不继续安装或更新。完成下面所需操作后，按第 4.2 节统一启动服务。

Adapter 安装、启用、健康检查和 `capabilities sync` 都是独立 CLI 操作，不要求 Connector 后台服务正在运行。`adapter start` 只启用 Adapter，不会启动 Connector 后台进程。

配对绑定的是设备上的 Linux Edge 连接器；安装或更新 Adapter 不需要重新配对。完成第 3.4 节的 systemd 配置并停止服务后，按需选择以下操作：

| 操作 | 适用情况 | 命令 |
| --- | --- | --- |
| 内置 Adapter | 首次安装程序自带的 Linux 采集能力 | `adapter install-builtin` |
| 自定义 Adapter | 安装具有新编号的独立适配器 | `adapter install` |
| 更新 Adapter | 保留已有编号，更新代码、能力和版本 | `adapter update` |

`start`、`stop`、`health` 使用 `adapter.json` 中的 `adapter_revision_id`，不是目录名或安装包名。升级时保持该编号不变，提升 `version`。

#### 4.1.1 内置 Adapter

适用于首次安装基础 Linux 采集能力。程序会自动生成 `adapter.json` 并安装自带的采集代码，无需手动创建清单。

内置编号为 `adapter_linux_system_inventory`，当前自带版本为 `1.0.0`，包含 `linux.inventory.read`。

```bash
# 安装内置 Linux 主机信息采集 Adapter（适配器）
qizhen-linux-edge adapter install-builtin

# 启用该 Adapter，使其可以处理平台下发的采集请求
qizhen-linux-edge adapter start adapter_linux_system_inventory

# 检查状态，预期返回 status: ready
qizhen-linux-edge adapter health adapter_linux_system_inventory

# 将已启用的 Adapter 及其能力同步到平台
# 当前内置能力为 linux.inventory.read：只读采集主机信息
qizhen-linux-edge capabilities sync
```

如果已通过第 4.1.2 节升级到 `1.1.0`，不要再次执行 `install-builtin`，否则会重新选择程序自带的 `1.0.0` 版本。

#### 4.1.2 安装或更新自定义 Adapter

先按第 4.1 节停止服务，再进入 Adapter 安装包目录。准备好 `.tar.gz` 安装包及对应 `.sha256` 文件，根据情况选择动作：

| 场景 | 动作 | 编号与版本 |
| --- | --- | --- |
| 首次安装一个新 Adapter | `install` | 使用安装包中声明的新 `adapter_revision_id` |
| 更新已有 Adapter | `update` | 保持 `adapter_revision_id` 不变，提升 `version` |

下面共用同一套校验、安装/更新、启用、健康检查与能力同步步骤。执行前修改 `action`、`package` 和 `adapter_id`；编号须与安装包内的 `adapter.json` 一致：

```bash
(
  set -e

  # 首次安装填 install；更新已有 Adapter 填 update
  action=install
  package=jetson-adapter-1.0.0.tar.gz
  adapter_id=adapter_jetson_system

  # 验证安装包并从校验文件读取 SHA256
  sha256sum -c "$package.sha256"
  digest=$(awk 'NR == 1 {print $1}' "$package.sha256")

  qizhen-linux-edge adapter "$action" "./$package" --sha256 "sha256:$digest"
  qizhen-linux-edge adapter start "$adapter_id"
  qizhen-linux-edge adapter health "$adapter_id"
  qizhen-linux-edge capabilities sync
)
```

例如，更新已准备好的 Linux 采集升级包时，将开头三个变量改为：

```bash
action=update
# 改为新版本安装包
package=linux-system-inventory-1.1.0.tar.gz

```

更新时，`adapter_id` 必须保持原编号，并与新安装包中 `adapter.json` 的 `adapter_revision_id` 一致。例如从 `1.0.0` 升级到 `1.1.0`，编号仍为 `adapter_linux_system_inventory`，只调整版本、代码、能力及安装包。更换编号属于安装另一个 Adapter，应使用 `install`，不能当作原 Adapter 的更新。

完成后按第 4.2 节启动后台服务。安装、更新、健康检查或同步失败时先处理错误，不继续启动服务。重新打包后需重新生成 `.sha256` 文件。

### 4.2 启动后台服务并检查

完成所需 Adapter 的启用、健康检查和能力同步后，在目标设备端执行：

```bash
systemctl --user start qizhen-linux-edge.service
```

若前面是更新操作，这一步恢复后台接收请求。安装、健康检查或同步失败时先处理错误，不要把失败的更新当作成功继续。已有单独 Adapter 安装/更新脚本自动启动服务时，再执行 `systemctl --user start` 不会重复启动实例。

若之前手动执行了 `qizhen-linux-edge run`，先在原终端按 `Ctrl+C` 退出，避免前台和后台同时运行。使用后台服务后，日常不再手动执行 `qizhen-linux-edge run`。

## 2026-10-19 staging 修复说明

本目录新增 Connector 0.1.1 源码与 wheel，修复 Adapter `ok:false` 仍上报成功的问题。
旧 0.1.0 文件保留，当前运行版本不会自动变化。源码及隔离测试见 `connector-source/README.md`。

Franka Adapter 2.2.0 的 workspace 配置应指向 `~/ribbon_ws` 根目录，
不再使用旧 `franka_ws` 或 `ribbon_ws/pipeline` 作为该配置值。
安装前先使用 Adapter 的 `scripts/check_runtime.py` 做只读路径检查；health只检查包/schema。

通用服务的 HOME 默认只读。Franka 原生调平需要写入状态、共享起点和审计目录，
部分程序使用已有 sudo 白名单；其专用服务 drop-in 示例在
`adapter-source/deploy/qizhen-linux-edge-franka.conf`。本次没有应用该配置、
迁移已安装配置、重启服务或调用设备。部署时另行确认并执行，不能直接把通用服务改为任意root执行。

平台上一次启动工具调用成功不等于实验完成；请查询返回的 session。
现场确认和取消通过 Adapter 的明确会话操作进行，仍按原有操作者授权流程处理。
