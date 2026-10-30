# Franka Ribbon 实验手册（实验上下文 + API 操作）

版本：2026-10-23（在 2026-10-22 版基础上增补网关操作者放行 `approved`、pro6000 adapter 2.3.10 会话快照顶层白名单、动捕资产改名 `ribbon_1021` / `x0` / `x1` 与端板法向偏移、ribbon 安装端 58 mm；此前版本已含任务根迁出 `pipeline/`、`tasks_root` 网关配置、运行根目录 `motion_summary.txt` 走法摘要与失败运行归档、检查点复用、起点校验、`return_to_start_joints`、SSH 网关队列与 prepare/execute 复用、ribbon 后处理默认只生成交互 HTML（两个 MP4 需 --ribbon-videos）），适用于本机 `/home/zhaoyunzyq/ribbon_ws/pipeline` 当前实现。
工作区布局（2026-10-22）：任务 YAML 与导出 CSV 的根目录是 `ribbon_ws/trajectories/`（2026-10-22 从 `ribbon_ws/pipeline/trajectories` 整体迁出，旧路径不再存在）；本目录属于 `ribbon_ws/pipeline/`；ROS 在 `ribbon_ws/ros/`，libfranka 在 `ribbon_ws/libfranka/`；动捕在 `ribbon_ws/Nokov/`（采集器
`~/ribbon_ws/Nokov/recorder/build/nokov_recorder`，数据 `~/ribbon_ws/Nokov/data/`），测力计在 `ribbon_ws/ati/`，USB 摄像头在
`ribbon_ws/camera/`。总览见 `ribbon_ws/README.md`。
本文由原 `FRANKA_RIBBON_CONTEXT.md` 与 `FRANKA_RIBBON_LLM_API.md` 合并而成；`RIBBON_FLANGE_MOUNT.md`（并入 3.1）
与 `RIBBON_WORKSPACE_CONVERSATION_SUMMARY_20260922.md`（并入第 3 章）随后也已并入并删除。**本文件是唯一手册**，
远程 `read_franka_manual` 读取的也是本文件（见 18.2）。

**启真平台 Adapter 2.3.13 手册入口：** `franka.manual.read` 改为固定读取当前安装包内的
[Agent 操作手册](AGENT_OPERATIONS.md)，不再返回本完整参考手册。本文保留实验背景、历史记录及
原生接口资料；原 2.3.11 的随包读取说明仅作为历史记录，不改变当前工具读取目标。

**启真平台 Adapter 2.3.11 会话约定：** 当时的 `franka.manual.read` 固定读取 Adapter
安装包内的本手册，按版本发布并返回 SHA-256，不读取 `ribbon_ws` 中的手册副本。
原生 extension 的 `read_franka_manual` 仍属于下文的原生工具参考。
本版 snapshot 的顶层字段由 adapter.json 的会话状态输出白名单固定；嵌套结果、确认和停稳证据、产物分页及控制锁行为保持原样。
`franka.pipeline.start` 必须提供 `task_id`。
每个新会话按所选 mode 从任务重新规划，并重新完成该 mode 要求的仿真、预检和执行阶段；
不开放检查点复用入口。本文 `--from-run` 的说明保留为原生 CLI 参考。
视频补录使用保存的轨迹和 marker，在新会话重新生成所选视频。相同 `request_id`
的重试仍返回原会话，明确开始新会话时须使用新的 `request_id`。

**启真平台卡片策略（2.3.5）：** 只有 `franka.session.respond` 声明为 high_impact，
其余操作不再触发平台 Tool 前置确认卡片。真实运动、设备权限、原生交互与当前提示
ID/允许动作校验仍有效，不能因取消平台前置卡片而自动代答。
独立 home/微动/CSV 不再生成 Adapter 额外的托管 MOVE/QUIT 等待，调用后直接
启动原生程序；原生程序不询问时不会弹卡片。受管理输入的冻结和启动前哈希复核保留。
仅在原生终端实际等待当前输入时，才通过 session.respond 展示并提交对应卡片。

**Adapter 2.3.6 停稳核验：** 每关节反馈速度绝对值须 <=0.01 rad/s，
两次采样的位置范围仍须 <=0.0001 rad；采样间隔 0.25 s、允许模式和无效数据拒绝规则不变。
这是 Adapter 的停稳判据调整，不清除原生调平的 run_pause，也不自动重试运动。

**Adapter 2.3.11 安装与动捕：** 当前安装端为法兰 +Z 58 mm，显式起点要求真实
`flange_58mm_v3` 标定；旧起点不可补标签冒充新标定。动捕监测、记录及单帧提取选择
`ribbon_1021`；带身 12 点是手册记录，实际可见点数以本次回执为准，不能要求每帧全点可见。
现场网关的 `approved` 由操作者通过本机入口放行，不能通过 Adapter 代填。

怎么读：

- **第一部分（第 1–6 章）**：接手实验前必须建立的背景——AI 角色与权限、任务目标、硬件装夹与试样、坐标与位姿约定、操作边界。
- **第二部分（第 7–17 章）**：按接口查阅的 API 手册——调用命令、参数、交互、回执、失败处置与任务 YAML 格式。
- **第三部分（第 18 章）**：远程托管工具（extension）、任务队列与视频说明。

## 更新记录

- **2026-10-23 启真平台 Adapter 2.3.11 源码同步**：同步 `flange_58mm_v3` 起点合同、58 mm
  宽面对齐说明和 `ribbon_1021` 动捕命令/单帧提取，更新随包手册与无硬件回归；保留旧版本包，
  不修改旧标定/实验数据，不安装或切换服务。修正第 10 章遗漏的旧资产名示例。见 18.2。

- **2026-10-23 动捕资产改名 `ribbon_1021` / `x0` / `x1` + 端板法向偏移**：Nokov 工程里的资产 2026-10-21 深夜
  改名（`ribbon` → `ribbon_1021`，12 点），2026-10-22 20:48 又把两块端板定名 `x1`（4 点刚体）/ `x0`（3 点刚体）；
  端点口径随之更正为**机械臂端 = `x1/Marker2`、固定端 = `x0/Marker3`**（与 2026-10-16 记录的
  `ribbon_x1/Marker1` / `ribbon_x0/Marker3` 不是同一套命名，旧记录只在旧资产下成立）。
  pipeline 于 2026-10-23 00:19 同步：`tools/ribbon_params.yaml` 与 `tools/ribbon_level.py` 的 `marker_sets`
  改为 `ribbon_1021`；`tools/franka_api.py` 的 `--plane` 与 `capture.marker_set` 回执字段同步改名；
  `tools/pipeline_videos.py` 的带身兜底 markerset 改为 `ribbon_1021`，近/远端点默认改为 `x1/Marker2`、
  `x0/Marker3`，`--end-z-offset-m` 0.025 → **0.028**（实测球心高于带子中心线 27.2 / 29.3 mm），并新增
  `--end-offset-mode {world_z,plate_normal}`（默认 `plate_normal`）：把该资产全部 marker 当刚体做 Kabsch，
  偏移方向随端板一起转，缺板点或残差 >5 mm 时逐帧退回 `world_z` 并计数；
  `tools/world_base_calibrate.py` 的默认资产/点名同步为近端 `x1/Marker2`、远端 `x0/Marker3`。
  自检（2026-10-23 00:04 静态抓取，181 帧，不动机器人）：`end_constraints.enabled=true`，
  `plate_normal` 用满 181/181 帧、0 次回落；端板水平时两种模式端点差 0.00 mm；拟合带长 1.000 m、
  宽度 RMS 0.64 mm、实测段 0.804 m（80%）、`end_gap` 90 mm。
  **历史数据不随之改名**：旧 run 的 CSV 仍写 `ribbon` / `ribbon_x0` / `ribbon_x1`，渲染旧数据要显式
  `--near-end-set ribbon_x0 --near-end-marker Marker3 --far-end-set ribbon_x1 --far-end-marker Marker1
  --end-z-offset-m 0.025 --end-offset-mode world_z`，否则端点读不到、`end_constraints.enabled=false`
  （只重建观测段，不报错）；网关 `render_videos` 补录旧任务时就是这种情况。
  单元测试尚未跟上：`pipeline/tools/tests` 当前 193 通过 / 12 失败，其中 5 项（`test_ribbon_geometry` 1 项、
  `test_world_base_calibrate` 4 项）是按旧资产名断言，其余 7 项是 2026-10-20 起既有的 ribbon 会话/快照用例。
  未做：端点扭转插值（把外推段 director 从未实测段单调过渡到端板滚转），需要一次带完整 180° 扭转的
  完整采集才能验证。见 3、10、15.6、18.1、18.2。

- **2026-10-22 安装端改 58 mm**：`fer_link8 → fer_ribbon_tcp` 由 `[0,0,0.008]` 改为 `[0,0,0.058]`
  （横向仍为零）；新标识 `flange_58mm_v3` / `FRANKA_RIBBON_GUARD_FLANGE_58MM_V3`。
  旧 8 mm 起点快照、旧 CSV/guard 不可复用；执行器只接受 v3，必须重新调平/标定后再规划。
  `pipeline_videos` 仍可读 v2 guard 做历史录像/世界系重建（几何取自链本身）。见 3.1、4.5、15.4。

- **2026-10-22 网关操作者放行（`approved`）**：新任务一律以 `approved = 0` 落库，调度器永远跳过；
  只有现场操作者在本机看板 <http://127.0.0.1:8770/> 点「确认执行」，或执行
  `robot_job approve --id <id>`（SSH JSON `approve`），任务才进入可自动派发状态。`approve` 只接受
  `queued`，并同时写 `acknowledged = 1`；提交参数无法预置放行，单独 `acknowledge` 不再足以启动。
  新增配置 `require_operator_approval`（默认 `true`，设 `false` 是显式回滚）；`jobs` 表新增 `approved` 列
  （旧库自动 `ALTER TABLE`），`queue_status` 每项新增 `approved`，`eligible` 改为按全部闸门计算，
  `health` 返回 `require_operator_approval`。`robot_job start` 仍是显式手动启动、不需要放行。
  pro6000 侧**没有对应工具**：放行必须由人在本机完成（见 18.2）。本次只改网关代码、看板与文档，
  没有登记或启动任何任务。

- **2026-10-22 pro6000 adapter 2.3.10**：`adapter_franka_ribbon` 由 2.3.9 升到 **2.3.10**：
  `franka.session.status`（`Broker.snapshot()`）改为按 `adapter.json` 的
  `franka.session.status.output_schema` **白名单**输出顶层字段，不再"复制内部会话再排除少数"，
  新增内部字段默认不进回执；result / confirmation / stop_verification 与产物条目的嵌套内容不变，
  产物分页、128 KiB 大结果处理、状态核验与控制锁规则保持原样。2.3.9 的任务根迁移、2.3.8 的
  `--force-stop` 清锁入口继续保留。这是输出边界收紧，不是新功能；安装包为
  `packages/franka-ribbon-2.3.10-amd64.tar.gz`，版本以 `adapter.json` 为准。见 18.2。

- **2026-10-22 任务根迁出 pipeline + 运行摘要 + 失败归档**：任务 YAML / 导出 CSV 的根目录从
  `~/ribbon_ws/pipeline/trajectories` 整体移到 `~/ribbon_ws/trajectories`（同盘移动，内容与哈希不变）。
  网关新增 `tasks_root` 配置（默认 `<workspace>/../trajectories`，即 `~/ribbon_ws/trajectories`），
  `list_tasks` / `read_task` 的边界改为该根，`health` 返回 `tasks_root`；不改 `Output/config.json` 也可用。
  `plan.launch.py`、4 个 MTC 节点的默认输出目录、5 个 MTC launch 的默认值、`check_host_readiness.sh`、
  `verify_robot_ladder.sh` 与全部文档同步到新路径；ROS 侧要 `colcon build` 后默认值才生效。
  每个运行根目录新增 `motion_summary.txt`（几句话写清走法，例如“沿 base +X 走 35 cm”
  “原地绕 base +Y 轴转 +5° ×6 次”），`franka_api` 运行目录与网关 job 根目录也各有一份；
  历史运行已回填 201 个文件，只新增文件、不改 `result.json`。
  `pipeline_runs` 中 65 个失败运行移入 `pipeline/archive/failed_runs_20261022/`（保留相对路径与
  `motion_summary.txt`，附 README 与 index.tsv）；`Output/jobs` 的失败任务按数据库保留，未移动。
  pro6000 adapter 源码同步：`Workspace.tasks` 改为 `<workspace>/../trajectories`，手册与 README 更新，
  版本升到 2.3.9；部署仍走包安装流程。本次修改不启动设备、不运动、不连接机器人。

- **2026-10-20 后处理默认只出 HTML**：`run_pipeline.py --mode execute` 运动结束后默认只生成
  `videos/ribbon_viewer.html`（以及 `ribbon.json`、`ribbon_fit_diagnostics.json`）；两个 MP4
  （`ribbon_fit.mp4`、`ribbon_only.mp4`）默认不再渲染，需要时加 `--ribbon-videos`，或事后用
  `pipeline_videos.py --ribbon-videos` / 网关 `render_videos` 补录。逐帧拟合仍保留用于质量指标，
  省掉的是 matplotlib 3D 逐帧光栅化和 MP4 编码；实测 85 s 运动的后处理从约 191 s 降到约 15–20 s。
  见 15.5、15.6、18.1。
- **2026-10-19 网关 prepare/execute 复用与远程确认**：SSH 任务网关新增 `list_runs` /
  `read_run` / `submit_resume` / `send_input`，pro6000 新增 `robot_pipeline_list_runs`、
  `prepare_robot_pipeline_from_run` 与 `robot_pipeline_confirm`。复用接受已有 `plan`/`prepare`
  运行，可生成不可变 prepare 或 execute 规格，源运行不动；execute 复用进入普通队列。
  运行中的 MOVE/HOME/RELEVEL/QUIT 提示可用 `robot_pipeline_confirm` 远程发送当前
  `pending_confirmation.choices` 中的精确答案，也可继续 attach；不再要求现场终端。
  见 15.9、18.2、18.3。
- **2026-10-19 pro6000 队列工具**：pro6000 的 ribbon-research hardware extension 已封装
  网关队列：`robot_pipeline_queue_status`（只读）、`robot_pipeline_queue_pause` /
  `robot_pipeline_queue_resume`（只阻止新启动）、`robot_pipeline_acknowledge`（仅手动
  tool-chat/tool-agent 上下文、仅 Experimentalist 后端角色）、`robot_pipeline_reorder`；
  `robot_pipeline_submit` 新增可选 `priority`。默认仍不代认、不代答、不重试；
  `acknowledged` 需单独动作；pipeline 的 MOVE 提示由用户明确选择后远程发送，
  不自动确认。已重启交互窗口才加载新工具；
  本次只改代码与文档，未登记或启动任何任务。见 18.2、18.3。
- **2026-10-19 任务队列与自动调度**：SSH 任务网关新增单实例 `worker` 调度器，
  远端可任意时间提交任意多个任务，按 `priority` 高者先、同优先级先提交先执行，
  逐个启动、一次一个。自动启动需同时满足 `auto_start=true`、未暂停、无活动或
  `needs_review` 任务、该任务已显式 `acknowledge`；启动前仍复核输入与配置哈希。
  `needs_review` 继续阻塞队列；`confirmation_timeout_seconds` 默认 0（不超时、不代答）。
  新增 `queue`/`acknowledge`/`reorder` 命令与同名 SSH JSON 操作，`submit`/`submit_api`
  支持 `priority` 与 `acknowledge_calibration_motion`。生产服务
  `zd-robot-gateway-queue.service` 已启用，但没有启动任何任务；两条旧 `queued`
  任务未确认，保持不动。见 18.3。
- **2026-10-19 回程关节自运动（`return_to_start_joints`）**：任务 YAML 新增顶层布尔
  `return_to_start_joints: true`。规划器在最后一段之后追加一段**保持 TCP 位姿的零空间自运动**，
  把七个关节送回 `start_state.joint_positions`；修正段逐点检查关节限位、冻结 X 下界与
  `/check_state_validity` 碰撞，任一项不通过就**跳过并 WARN**，本次 plan 仍成功。轨迹 YAML 新增
  `joint_return` 记录与一个 `motion: joint` 段；`ribbon_feasible_20261018` 的 15 份任务已启用，
  15 份的 `plan` 与 `prepare`（Gazebo 回放 + preflight）均已通过；preflight 仅有可操作度 WARN
  （0.024–0.033，<0.05，默认自动继续），无 FAIL。与 `home_pose` 不同：它不是关节空间直线插值，
  TCP 全程不动，X 下探约 0，且受 X guard 约束。见 15.9.4、16.2、16.4。
- **2026-10-18 检查点复用与起点校验**：`plan`/`prepare` 成功后写 `checkpoint.json`；
  `--from-run <plan|prepare运行> --mode execute` 在新目录复用 task/trajectory/guard/仿真，跳过调平与规划，
  但预检、`robot_prepare`、最终 `MOVE` 和采集都不跳过。execute 前按**关节空间**比较当前起点与
  `trajectory.csv` 首点：`<=0.008 rad` 直接执行；`0.008–0.20 rad` 且 guard FK 包络（TCP 1 mm、朝向 2°、
  X 0.65 mm）通过时可输入 `HOME` 用 `home_pose` 归位；更大或路径不安全必须重新调平+规划
  （`RELEVEL` / `START_STATE_DRIFT`）。执行结束**不会**自动回起点；需要时手动 `home_pose`，或在下一次
  `--from-run execute` 的起点校验中选 `HOME`。见 15.9、12、15.1、15.3–15.7。
- **2026-10-18 远端 YAML 任务入口**：extension 新增 `robot_pipeline_list_tasks` 与
  `prepare_robot_pipeline_remote_task`，可按 r9000p 上已有任务 YAML 的路径准备任务，再走原有的
  `robot_pipeline_submit` / `robot_pipeline_start`，不再只能从结构化参数生成规格；
  8、16、18.2 的入口说明与映射表已同步。
- **2026-10-18 YAML 交付验证门槛**：新增 15.2.1，编写或修改供机械臂执行的 YAML，必须通过
  prepare 的完整规划、仿真及预检后才能标记为“离线验证完成”；默认先用
  --mode prepare --skip-leveling，明确默认起点与真机调平起点的证据差别。
  静态解析不作为完成依据，末尾回程同样必须验证；第 1、16 章增加入口提醒。
- **2026-10-16 合并与补齐**：两份手册合并为本文件，并补齐此前漏记的内容——第 11 章的调平方向门禁
  `axis_ratio_min`、第 15.5 节的 `--no-force-plot`、第 15.8 节的 ATI 网络前提 / 标定退化 / 首次上机实测；
  ribbon 视频文字统一为 2026-10-14 的 rod_offset 修正版（原 CONTEXT 里那份未修正的旧说法已删除）。
- **2026-10-16 合并第二批**：`RIBBON_FLANGE_MOUNT.md` 全文并入 3.1，原文件删除；
  `RIBBON_WORKSPACE_CONVERSATION_SUMMARY_20260922.md` 里本手册引用的材料参数出处与球形边界依据并入第 3 章，
  原文件删除；`docs/PIPELINE.md` 中两处过时状态（仿真默认开界面、ATI 接入尚未上机）已更正。
- **2026-10-16 力采集接入**：`run_pipeline.py --mode execute` 在动捕启动的同一时刻再启动一路 ATI Mini45
  六维力测量（`ati_capture` → `~/ribbon_ws/ati/ati_capture_adapter.py`，默认 `172.16.0.5:49152`），默认开启、
  与动捕同等严格；见 5.1、15.0、15.5、15.6、15.8。
- **2026-10-14 仿真与录像**：仿真阶段默认不启动 Gazebo 图形客户端，`--gui` 才开界面；`--video`
  默认开启，`--ribbon-video` 默认开启但只生成交互 HTML，两个 MP4 见 2026-10-20 记录；
  录像只是旁证；机械臂视频只用原生相机画面，不再生成骨架替代视频。见 5.1、15.1、15.5、15.6、18。
- **2026-10-13 交互与采集**：调平动作自动逐条执行（不再逐次 `MOVE`，可 `RESUME`/`SKIP`/`QUIT`）、
  `home_pose` 不等待 Enter、`cartesian_delta_move` 无确认闸门、真机轨迹期间默认采集 Nokov、远程工具封装。
  见 5.1、12、13、15.0、18。
- **2026-10-12 直连安装**：默认无抓手，控制点为 `fer_ribbon_tcp`（`fer_link8` + 局部 Z 8 mm，2026-10-22 改为 58 mm），
  旧标定、旧 CSV/guard 不可复用；先重新调平标定再规划。见 3.1、4.5。

---

## 第一部分 · 实验上下文：AI 角色、任务目标与硬件

### 1. 你的身份与工作职责

你是本机 Franka–ribbon 实验的 AI 操作助手。你的职责是理解用户的实验意图，结合已知的装夹与坐标关系，选择合适的接口，通过终端调用程序、必要时编写 YAML，并根据机器人状态、动捕数据和执行回执说明结果。

你可以协助观测当前形状、查看机器人状态、调平 ribbon、进行小幅位姿调整、返回已保存起点，以及规划和执行边界条件实验。根据本次任务选择接口；并非每次都要运行完整 pipeline。只要求观测时，使用观测接口；需要完整调平→规划→仿真→执行时，再使用 run_pipeline。

你不是实时控制器：1 kHz 控制由底层程序完成。你应保留用户指定的实验条件和程序已有检查，识别观测与推断的区别，不编造设备状态、材料限值或实验成功。

**YAML 撰写交付门槛：** 为机械臂新建或修改加载路径时，必须执行第 15.2.1 节的 prepare 验证。
仅表格换算或静态解析通过不能报告“已完成可执行轨迹”；未通过完整验证的文件只能作为未验证草稿交付，
并明确尚未完成的检查。新增回程、更改角度方向、扫描范围或停留/速度后，同样适用。
用户明确要求仅转换、仅静态检查或禁止运行时，遵守该限制，但不得因此把草稿标记为已验证。

#### 1.1 目标模型的权限边界

你的交互能力只有**终端**。文件操作、运行 API、读取命令输出和结果都通过终端完成；不能操作桌面、浏览器、RViz、Gazebo 或 XINGYING 的图形界面，也不能借助其他工具浏览主机文件。

| 行为 | 权限 |
|---|---|
| 阅读预先存在的资料 | 仅限 `~/ribbon_ws/pipeline/docs/` 内的文档与文档示例（本机绝对路径 `/home/zhaoyunzyq/ribbon_ws/pipeline/docs/`） |
| 创建/写入文件 | 可在任意位置写任务所需文件，例如 YAML、分析脚本、结果摘要和图片；使用明确路径，避免覆盖已有实验结果 |
| 阅读任务文件 | 可读取本任务过程中自己编写或 API 生成的文件，位置不限，例如任务 YAML、日志、CSV、JSON、快照 |
| 查看源码/现场配置/历史数据 | 不因路径已知或出现在文档中就获得读取权限。docs 外的既有源码、配置和旧实验文件不能自行展开阅读 |
| 调用程序 | 可以通过终端调用 API 手册中的命令；程序运行时自行加载安装文件、配置和依赖，不等于允许你直接阅读这些文件 |
| 图形界面核对 | 交给现场操作者；你只能读取终端输出与本任务生成的数据，不宣称自己看过现场或 GUI。仿真默认无界面（见 5.1）；`--video` 产出的录像属于本次任务产物，你可以报告它的路径/大小/哈希，但不能宣称看过画面内容 |

这些权限对 `cat`、`rg`、Python 文件读取以及其他间接读取方法同样有效。不能把禁止读取的既有文件复制到 docs 或新目录，借“任务生成文件”名义读取，也不能通过程序反射/转储绕过。`--help`、状态查询和已文档化的静态校验属于终端 API 调用，可以使用。

读取未知路径前判断它是 docs 内文档，还是本任务生成的文件；两者均不满足时，依据手册操作或请操作者提供所需事实。docs 中历史说明若与命令回执不符，保留差异并报告，不通过查源码自行补全。

### 2. 当前主要任务目标

通过机械臂末端位姿控制 ribbon 的可动端，为 ribbon 施加不同的位置和朝向边界条件，观察其弯曲、扭转及其他形状变化。一端由环境中的夹具固定，另一端由机械臂末端夹持。

当前已有流程支持自动测量、先宽面对齐再自动逐条执行的调平、YAML 途经点规划、Gazebo 预演（默认无界面，默认录制 Gazebo 相机视频，可用 `--no-video` 关闭）和真机执行；也提供独立归位、微动、CSV 执行与 Nokov 观测接口。用户已经进行了少量示例验证，这不代表任意新路径均已验证。

每次任务按用户要求明确：

- 要观测还是要运动；要达到什么端部位置/朝向，或检查什么形状指标。
- 位移和旋转的轴、正负、参考起点、执行顺序及停留时间。
- 是否需要调平、规划/仿真、真机执行，以及运动期间是否需要采集。
- 哪些量来自现场测量，哪些是用户给定条件，哪些尚待明确。

完成后报告本次实际做了什么、是否发生运动、是否达到接口成功条件、是否采集，以及数据/回执路径。失败时说明停止在哪一步、是否可能已经发生部分运动。

### 3. 当前硬件、装夹与试样

以下 L、b、t、E 由用户于 2026-09-22 直接给出，并已于 2026-09-27 确认仍为当前试样；这些是**用户给定的名义值，不是本机测量结果**。材料名称、允许应变、最小弯曲半径、两端是否允许转动、夹具固定点坐标、夹持点偏移与裕量都还没有提供，不得自行推测或补默认值。

| 项目 | 当前配置 / 含义 |
|---|---|
| 机械臂 | Franka Emika Research（FER），七个机械臂关节；本机 ROS 2 Humble、libfranka 0.8.0 |
| 真机连接 | FCI，机器人 IP `172.16.0.3`；现有主机配置使用 `eno1`、`172.16.0.1/24` |
| 规划控制点 | `fer_ribbon_tcp`；法兰 +Z 58 mm 的 ribbon 端点（见 4.5） |
| 固定端 | ribbon 一端由夹具固定在实验环境中；不会随机械臂运动 |
| 可动端 | ribbon 另一端由机械臂末端夹持，机械臂通过端部位置和朝向施加边界条件 |
| 有效长度 L | **1 m**（用于描述有效 ribbon 长度，不是当前弯曲状态下的两端直线距离） |
| 宽度 b | **24 mm = 0.024 m** |
| 厚度 t | **2.4 mm = 0.0024 m** |
| 弹性模量 E | **2.44 GPa = 2.44 × 10⁹ Pa** |
| 硬度 | 未提供独立的硬度测量值和标尺；弹性模量不是 Shore/Rockwell 等硬度值 |
| 材料名称 | 尚未记录，不依据弹性模量猜测材料 |
| 动捕 | Nokov / XINGYING；当前 server 参数为广播网卡地址 `10.1.1.198`，本机使用 Z-up |
| 六维力 | ATI Mini45（Net F/T 接口盒），设备 `172.16.0.5`、UDP 49152、约 50 Hz；只有 `execute` 真机轨迹期间默认记录，标定不可用时只有原始 counts（见 15.8） |
| 当前观察侧 | Markerset 名 **`ribbon_1021`**（即 `tools/ribbon_params.yaml` 的 `marker_sets`；2026-10-22 前叫 `ribbon`），必须原样匹配；它是资产名称，不能据此推断为机器人 base +Y |
| 端点识别 | 当前 `gripper_end: max_x`：动捕可见点中 X 最大端为夹爪端，X 最小端为固定端 |
| marker 资产 | 在线资产：带身 **`ribbon_1021`（12 点）**、机械臂夹持端 **`x1`（4 点 Marker1–4，刚体）**、固定端 **`x0`（3 点 Marker1–3，刚体）**；两块端板用于端点锚定与滚转解算（当前默认端点 `x1/Marker2`、`x0/Marker3`，见 15.6 之后的 2026-10-23 段）。2026-10-12 记录的旧 `ribbon`（10 点 `+y01`–`+y05`/`-y01`–`-y05`）与旧 `ribbon_x0`/`ribbon_x1` 已在资产里改名，历史 run 的 CSV 仍写旧名。仓库里的 `~/ribbon_ws/Nokov/recorder/assets/ribbon+y.mars`（6 点 Marker1–6）仍只是未启用模板。这是文档记录，不能直接读取 docs 外的资产文件；在线实际资产及可见数量用 list/本次记录核对 |

装夹示意：`环境固定夹具 ── ribbon（可弯曲/扭转）── 机械臂末端夹持点`。操作模型按端部夹持理解；“固定”不代表程序已测得夹具转动刚度、夹持滑移或六自由度理想固支。用户已确认参考装夹中长轴从机械臂夹持端指向固定端为 base +X，宽度沿 Y、厚度沿 Z；正方向与 tool 对应见第 4 章。实际夹持偏移、固定端绝对位置、装夹允许载荷、允许应变和最小弯曲半径尚无实测确定值。

#### 3.1 法兰直连安装与夹持方式（2026-10-12；2026-10-22 改 58 mm）

用户给定（2026-10-12）：抓手已拆除，黑色夹块上下夹持 ribbon，末端齐平；当时灰色连接件厚 8 mm，ribbon 端点中心对齐法兰中心。
**2026-10-22 用户把安装端中心改为沿法兰 +Z 58 mm、横向偏移 0**；连接件/夹块的实际外形仍未测量。
坐标链为 `base → … → fer_link7 → fer_link8 → fer_ribbon_tcp`：`fer_link8 → fer_ribbon_tcp` 的平移为
`[0, 0, 0.058] m`、旋转为单位阵；link7→link8 的 107 mm 是机器人本体结构，保留；旧 hand TCP 的 103.4 mm
和 hand 的 −45° 偏转已移除。TCP 原点位于 ribbon 安装端，**不是**黑色夹块外沿的自由段起点；可选球形工作空间
的长度、固定端 anchor 与 margin 也必须按同一端点定义测量（见 4.6）。

- **链路**：FER URDF/SRDF、MoveIt 和 Gazebo 默认无抓手，规划组末端为 `fer_ribbon_tcp`；`hand:=true`
  只用于显式生成旧抓手描述，旧抓取 MTC 示例不适用于当前硬件；驱动与只读发布默认 `finger_state_source=omit`。
- **一致性**：YAML 默认末端、ribbon profile、X 下界、导出的 FK 链、离线执行 guard、预检和离线 FK 工具
  统一使用新点；标定保存 `start_state.ribbon_mount: flange_58mm_v3`，ribbon 规划拒绝旧快照（pipeline 前置
  语法检查允许读旧起点，但真正规划必须在重新标定之后）。
  现有 `config/franka_start_pose.yaml` 仍是 2026-10-21 的 8 mm 时代快照（保留 `flange_8mm_v2`），
  下次调平成功后由 `ribbon_level` 改写为 `flange_58mm_v3`；不要手工改 tag。
  同理 `tools/state/world_base.yaml` 的 `connector_m` 仍是 0.008，下一次 `world_base_calibrate` 会重写；
  标定失败沿用旧值时，世界系/视频重建会偏约 50 mm，必须在 result 里确认已重新标定。
- **guard**：内容版本为 `FRANKA_RIBBON_GUARD_FLANGE_58MM_V3`，执行侧拒绝旧抓手与旧 8 mm 安装的保护文件（`pipeline_videos` 可读 v2 做历史重建）；CSV 中 `ribbon_guard_v1`
  列仍作为「必须携带保护文件」的兼容标记，几何版本由 sidecar 控制。
- **重新使用的前提**：更换抓手/安装或旧快照失效后，必须重新运行 ribbon 调平/标定，再重新规划及预检；
  不要给旧快照手工补新标识，不要复用旧 CSV。这里的“旧 CSV”指旧安装/旧标定快照；同一
  `flange_58mm_v3` 安装、同一起点下的 plan/prepare 检查点复用见 15.9，两者不是一回事。
  启动新环境前关闭旧 MoveIt / `robot_state_publisher` 进程并重新 source `~/ribbon_ws/ros/install/setup.bash`。
  默认 `home_pose` 读取实测关节起点，也应先重新标定再使用其默认目标。
- **边界与缺失项**：软件 TCP 轴平行法兰，这是坐标定义，不是材料宽度/厚度轴的测量结论；旧 tool X/Y 对应
  关系失效，tool Z 与法兰 Z 同向；基于 base 轴的任务维持原轴定义。连接件直径、夹块长宽厚、质量/质心/惯量
  尚缺，未虚构碰撞外形或负载——当前碰撞模型覆盖机械臂，**不覆盖新夹具和可变形 ribbon**；58 mm 是几何端点
  偏移，不表示夹具整体长度只有 58 mm。FCI 的 `O_T_EE` / `F_T_EE` 仍是控制器报告的工具变换，未冒充新 TCP，
  也未自动写入控制器负载；规划与 guard 由关节角和模型算 ribbon 端点。调平用的 `cartesian_delta_move` 是
  base 纯平移、姿态不变，各刚性连接点平移量相同，不需要补旋转杠杆臂。

**宽面法向约定（2026-10-12 晚补充）**：用户确认宽面法向与标准抓手安装后的两指连线同向，方向上对应法兰
坐标 `[1/√2, 1/√2, 0]`（标准 hand 的 +Y），**不等于法兰 +Y**。调零 ORIENT 步骤用该方向对齐 base +Z，
并固定法兰外 58 mm 的连接点旋转。此前「材料宽厚方向尚待确认」「调平只做纯平移」描述的是增加 ORIENT 之前
的状态；后续 LEVEL/TENSION 仍是原有纯平移。软件 TCP 坐标仍平行法兰，无需恢复抓手几何。
该次变更本身只做了离线构建、模型/配置回归与无硬件规划执行验证，未操作真机。

#### 3.2 材料刚度估算（解释性）

用均匀矩形截面、线弹性、夹持不滑动假设可估算：

| 量 | 公式 | 估算值 |
|---|---|---|
| 截面积 | `A = b t` | `5.76 × 10⁻⁵ m²` |
| 轴向刚度 | `EA/L` | `1.40544 × 10⁵ N/m ≈ 140.5 N/mm` |
| 弱轴弯曲刚度（沿厚度方向挠曲） | `E b t³/12` | `0.06746 N·m²` |
| 强轴弯曲刚度（沿宽度方向挠曲） | `E t b³/12` | `6.746 N·m²` |

这些是解释性估算，不是允许载荷或保护阈值。E、b、t 当前不进入 pipeline 的材料仿真；不要将它们直接添加进任务 YAML（未知字段会报错）。纯单侧 marker 点列也不足以完整恢复 ribbon 宽度方向姿态或扭转角。

由这组参数只能得到几何上的**必要条件**：设夹具固定点为 a、机械臂夹持点为 p，忽略轴向伸长时有 `‖p − a‖ ≤ L = 1 m`，即以固定点为球心、1 m 为半径的球是夹持点位置的外包络，还必须与机械臂自身可达范围、关节限制和无碰撞空间取交集。球内位置仍可能过度弯曲、扭转、碰撞或形变不稳定；两端夹紧并限制朝向时，完整约束还取决于末端姿态和到达路径。这就是可选 `ribbon_workspace` 检查的几何依据，它只做规划后筛查：不模拟弯曲形状、扭转、应力、稳定性或接触，也不自动补检旧 CSV。当前因缺固定端实测坐标、真实 `grip_offset` 与经实验确定的 margin 而不启用（见 4.6、16.5）。

### 4. 坐标系、单位与位姿参考

#### 4.1 三类坐标系

| 坐标系 | 用途与约定 |
|---|---|
| 机器人 base | 机器人固定基座坐标系；规划位置和独立微动的平移方向均在此表达 |
| 工具 tool / TCP | 随末端转动的局部坐标系；规划目标 link 为 fer_ribbon_tcp；原地旋转的实际夹持点运动取决于夹持偏移 |
| Nokov 世界系 | 当前本机 Z-up，marker 坐标单位 mm；与机器人 base 之间不能只换单位，还需外参变换 |

机器人位置输入通常为 m，关节角为 rad；YAML 的 angle_deg/RPY 使用度，orientation_tolerance 使用 rad。Nokov 坐标为 mm。1 mm = 0.001 m。

#### 4.2 不同接口的参考起点

| 接口 | 位置/朝向参考 |
|---|---|
| ribbon YAML / run_pipeline | 所有 position 相对同一个本次调平后冻结 TCP 位置，方向沿 base；rotation 相对本段起始朝向 |
| cartesian_delta_move | 相对调用时当前末端命令位姿，平移与旋转轴均沿 base；不是相对最近调平起点 |
| home_pose | 文件保存的七关节目标；“home”不是出厂零位，文件可能被最近一次调平更新 |
| execute_offline | CSV 中七关节绝对角度及时间，不接受笛卡尔相对位移 |
| Nokov | 动捕世界系中的 marker 点，不是机械臂目标坐标 |

#### 4.3 规划位姿与装夹方向的解释

控制对象为 `fer_ribbon_tcp`。若真实 ribbon 夹持点与该 TCP 不重合，原地旋转 TCP 也可能使实际夹持点平移；必须依据装夹标定解释位姿。

设本次调平后的 TCP 位姿为 `(p₀, R₀)`，第 i 段起始朝向为 `Rᵢ₋₁`：

| YAML 表达 | 实际含义 |
|---|---|
| `position: [dx, dy, dz]` | `p_target = p₀ + [dx, dy, dz]`，向量在 base 中，单位 m |
| `keep_orientation: true` | 锁定本段起始朝向，沿途按容差检查 |
| `rotation: {axis: z, angle_deg: 30, frame: tool}` | `R_target = Rᵢ₋₁ · Rz(30°)` |
| `rotation: {axis: z, angle_deg: 30, frame: base}` | `R_target = Rz(30°) · Rᵢ₋₁` |
| `keep_orientation: false` 且不填朝向 | 目标朝向回到任务初始 `R₀`，并非保持上一点朝向 |
| 绝对朝向字段 | 在 base 中定义朝向，不因 `position_reference: start` 而变为相对朝向 |

转角按右手规则。连续两次同一工具轴 `+30°` 会累积；若要从 `+30°` 回到初始朝向，可接同轴 `-30°`，或使用“不锁定且省略朝向”的目标初始朝向语义。多轴旋转不可交换顺序。

当前调平代码先按 4.5 做宽面对齐，再沿 **base −X 拉直、+X 松开、Z 升降**；这是本机既定装夹布局，不能据此推断另一种装夹的方向。Nokov 的 `max_x` 端点识别属于动捕测量坐标，不等同于可任意交换的机器人坐标轴。长/宽/厚方向已由用户明确，按第 4.4 节转换；仅在“前进”等措辞未确定正负或旋转顺序时进一步明确，不重复询问已有轴向。

本接口给出的是端部位姿边界条件。它不把目标曲率、张力、屈曲模态自动反解为位姿，不保证 ribbon 形状或应力。对未提供的材料限值、固定端坐标、夹持偏移，不编造数值。

#### 4.4 旧抓手历史参考（新安装不适用）：ribbon 的长轴、宽度、厚度与 base/tool 的对应

**用户于 2026-09-27 确认：长轴从机械臂夹持端→固定端为 base +X，宽度沿 base Y，厚度沿 base Z；base 和 tool 均为右手系。** 本文把材料正宽度定义为 base +Y、正厚度定义为 base +Z，则 `+L × +W = +T`。负方向分别相反，不再采用先前“固定端→机械臂端为 +L”的约定。

| 材料正方向（参考装夹） | base | 保存的调平姿态中的 tool 近似对应 |
|---|---|---|
| +L：机械臂夹持端→固定端 | +X | **+Z** |
| +W：正宽度方向 | +Y | **+X** |
| +T：正厚度方向 | +Z | **+Y** |

因此，向固定端移动/减小两端跨距使用 base +X，远离固定端/拉伸使用 base −X；当前 ribbon 任务的冻结 X 下界禁止负 X 目标偏移，不因材料正方向的定义而取消该保护。宽度方向位移填 position 的第二分量，厚度方向位移填第三分量。

**tool 对应关系的核对依据：** 维护者读取了保存时间为 `2026-09-27T15:36:17` 的调平关节快照，使用对应导出轨迹的 base→fer_hand_tcp 运动学链计算，并与轨迹第一段的 `start_orientation_xyzw` 交叉核对。以下数字已写入 docs，目标模型无需、也不得自行阅读原始 docs 外历史文件。它们描述保存姿态，**不是本轮在线读取的当前机器人姿态**。

该姿态的 `R_base_tool`（将 tool 向量映射到 base，列分别为 tool X/Y/Z）为：

```text
[[-0.016364928, -0.028052029,  0.999472497],
 [ 0.998617375, -0.050400842,  0.014936335],
 [ 0.049955261,  0.998335033,  0.028838050]]
```

TCP 的 base 位置为 `[0.401335197, -0.018553456, 0.597054563]` m。tool +Z 与 base +X 夹角约 1.861°，tool +X 与 base +Y 约 3.013°，tool +Y 与 base +Z 约 3.307°，所以表中只是近似轴对应。两个坐标系均为右手系本身不足以确定变换，这里的对应来自保存姿态的运动学计算。

在此参考姿态：

- 要**严格绕 base 长轴**正向转 θ，使用 `rotation: {axis: x, angle_deg: θ, frame: base}`。
- 要**绕随末端转动的工具 Z 轴**转 θ，使用 `rotation: {axis: z, angle_deg: θ, frame: tool}`。它在参考姿态近似绕 ribbon 长轴，但不等价于严格绕 base X。
- 严格绕 base 宽度/厚度方向转动分别选 base y/z；参考姿态近似对应 tool x/y。正角按对应正轴的右手规则。
- 平移始终以 base 表达，YAML 的各 position 仍相对同一个冻结起点。tool 方向位移 d 要先算 `Δp_base = R_base_tool * d_tool`。

后续姿态变化时，用**本任务生成的** `trajectory.csv.yaml` 中相应段的 `start_orientation_xyzw` 更新 R，不能沿用上表。材料方向在 tool 中可用 `u_tool = Rᵀ*u_base` 表达；通常不是精确的单个 x/y/z 分量。若要求绕实际材料轴而它不与工具轴重合，不能选“最接近”的轴冒充精确旋转；应从完整 R 计算绝对目标朝向，或直接使用用户要求的 base 轴。

#### 4.5 法兰直连的 ribbon 端点

取消抓手；ribbon 端点中心相对法兰外侧沿 +Z 为 58 mm，横向偏移为零。
新 `fer_ribbon_tcp` 的原点就是该端点，坐标轴平行法兰。
`ribbon_workspace.grip_offset` 若用于此端点应为 `[0,0,0]`，不可再添加 58 mm。
上节保存姿态、tool X/Y 对应关系和数值矩阵来自旧抓手，只保留作历史记录；新安装的数值必须重新计算。
当前调平默认启用宽面朝上对齐（`tools/ribbon_params.yaml` 的 `align_ribbon_up: true`）：按现行约定，宽面法向对应法兰方向 `Rz(−45°)·[0,1,0]`，程序以 `cartesian_delta_move --align-ribbon-up` 只做旋转、每步最多 2°、误差超过 20° 暂停，连接点保持法兰外 58 mm。该约定由维护者按现场安装标定；安装角度改变时先请维护者确认，不能在任务里自行套用别的 tool 轴对应关系。

#### 4.6 固定端 base 坐标与 margin：当前不启用可选球形检查

**当前决定：普通任务省略 `ribbon_workspace`，保留既有强制 X 下界与 guard。** 固定端绝对坐标和 margin 没有实测依据，而用户仅在启用此可选检查时需要它们，因此本配置不杜撰参数，也不为这项未启用的检查阻塞普通任务。

可作几何估算但不能当作实测：假设 ribbon 完全直、无伸长、有效长度恰为 1 m、夹持点与 TCP 重合，则参考姿态有 `anchor_nominal = p_TCP + [1,0,0]`，约为 `[1.401335197, -0.018553456, 0.597054563]` m。实际跨距可能因下垂、装夹和伸长而不同；**不把这个估计写入可执行的 ribbon_workspace**。

也不随意指定 0.02 m 裕量：若调平后端距接近 1 m，检查要求 `distance ≤ 1.0 − margin`，正裕量本身就可能拒绝起点；取 margin=0 又没有误差余量。将来用户明确要求该检查时，再用固定端实测坐标、真实 grip_offset 和经实验确定的 margin，满足 `0 ≤ margin < 1.0`。Nokov 坐标转换到 base 还需外参，不能只把 mm 除以 1000。

### 5. 操作边界与结果解释

- 按用户已授权范围操作。缺少物理轴、装夹、现场状态等必要信息时，说明缺少什么；不重复索要已经明确的授权。
- 使用接口现有的交互确认，不预填连续确认词。不同接口的确认方式不同，以本手册第二部分为准。
- 保留冻结起点、ribbon guard 与失败检查；不通过降低边界、修改导出轨迹或伪造回执使任务“通过”。
- 仿真通过、程序退出、文件存在和物理实验成功是不同结论。按当前调用的实际回执与测量判断。
- 仿真录像（`--video`，见 5.1 与第 15.5/15.6 节）只是可视化旁证：它不改变仿真判据，
  缺录像或录像失败只写告警（`result.json` 的 `simulation_video_warning`），也不代表真机表现。
- 力采集（`ati_capture` → ATI Mini45，见第 15.8 节）与录像一样只是记录：它挡住的是“缺数据仍继续上机”，
  不改变任何通过判据；标定不可用时只有原始 counts（`calibrated=false`），不得当力值或力学结论报告。
- USB 摄像头录像（`usb_capture` → `camera/usb_capture_adapter.py`，见第 15.10 节）与动捕/力采集
  同等严格：它挡住的是“缺视频仍继续上机”，同样不改变任何通过判据；默认 1920x1080@30，
  没有视频时不能把“程序退出 0”当作已录到画面。
- 仿真默认无界面不等于“仿真降级”：跟踪误差、记录覆盖、预检判据与开界面时同源。
- 失败可能发生于部分运动之后；先查当前状态和日志，不自动重发、归位或重放旧 CSV。`--from-run` 执行前的
  起点校验是另一条路径（15.9），不是失败后的自动补救；归位仍需操作员 `HOME` 确认。
- 当前工具主要实施位姿边界条件；没有以 ribbon 张力、曲率或完整形状为目标的闭环控制。默认任务执行不发送夹爪开合，不因“夹持”一词自动改变夹爪。
- Nokov 单侧点列是有限采样观测，不足以完整恢复全宽扭转或材料应力。旧记录只能说明当时状态。

#### 5.1 已确认的执行条件：授权到 execute（部分条目已被 2026-10-13 更新取代，见下）

> **2026-10-13 更新——下列三项取代本节 2026-09-27 记录的对应条目，其余条目（授权上限 execute、调平交互、最终 MOVE、保护与边界检查）一律不变：**
> · **运动期间采集：已启用。** `tools/pipeline_adapters.yaml` 的 `nokov_capture` 指向 `~/ribbon_ws/Nokov/nokov_capture_adapter.py`；`run_pipeline.py --mode execute` 在整段真机轨迹期间持续记录 ribbon markerset，成功结果为 `executed_and_captured`。置回 `null` 即恢复不采集（`executed_without_capture`）。
> · **采集适配器：已接入**，与调平阶段共用同一个 `nokov_recorder`（XINGYING C++ SDK），不是另写一套 SDK 调用。
> · **名义夹持点：`fer_ribbon_tcp`**（`fer_link8` + 局部 Z 0.058 m），不再是 `fer_hand_tcp`；后者只在 xacro `hand:=true` 生成带手模型时存在。
> 依据：2026-10-12 直连安装变更，以及用户 2026-10-13 明确要求记录运动过程中的 ribbon 点。

> **2026-10-14 当前仿真与录像（不改授权）：** `run_pipeline.py` 的 `simulate`
> 阶段默认**无 Gazebo 界面**，`--gui` 才开界面；默认开启 `--video`，在无界面下把
> 整段回放（含引导段）录成 `pipeline_runs/<run>/simulation/gazebo_review.mp4`。
> 最终任务轨迹的 `MOVE` 确认与其它保护一律不变；无头时确认前的提示改为指向该录像、
> `simulation/report.txt` 与 `actual.csv`。录像不参与通过判据；真机执行段没有视频
> （仿真在真机运动前关闭以释放主机）。相机设置过重会让仿真变慢甚至 `SIMULATION_FAILED`，
> 因此不要为“看得更清楚”要求现场调高分辨率/帧率，除非重新验证。

> **2026-10-16 力采集已接入（不改授权）：** 按用户要求，`run_pipeline.py --mode execute`
> 在动捕启动的同一时刻再启动一路 ATI Mini45 六维力测量（`tools/pipeline_adapters.yaml`
> 的 `ati_capture` → `~/ribbon_ws/ati/ati_capture_adapter.py`，默认设备 `172.16.0.5:49152`）。
> 默认开启且与动捕同等严格：收不到力数据、中途断流或未覆盖运动时段都会以 `FORCE_*`
> 中止，不会在缺数据时继续真机运动；`ati_capture: null` 即关闭。运动结束后自动生成
> `force/force.png` 与 `force/force_plot.json`（`--no-force-plot` 可关；绘图失败只记
> WARN，不影响任何判据）。授权上限、MOVE 确认、X guard 与预检阈值一律不变；
> 调平阶段不使用力传感器。

> **2026-10-18 USB 摄像头录像已接入（不改授权）：** 按用户要求，`run_pipeline.py --mode execute`
> 在 Nokov 动捕和 ATI 力采集开始工作、机械臂开始执行轨迹的同一时刻，调用
> `camera/usb_capture_adapter.py` 开始录像；运动停止时摄像头一起停止。默认 **1920x1080 @ 30 fps**、
> 输入 MJPEG、输出 H.264 mp4，并落盘逐帧 `wall_unix_ns` 时间戳 CSV（与 Nokov/ATI 同源可对齐）。
> 默认开启且与动捕/力采集同等严格：摄像头打不开、中途断流或未覆盖运动时段都会以 `CAMERA_*`
> 中止，不会在缺视频时继续真机运动；`usb_capture: null` 即关闭。授权上限、MOVE 确认、
> X guard 与预检阈值一律不变；调平阶段不使用摄像头。

**用户已明确：运动期间采集已启用，授权到 execute。** 在本实验任务范围内，后续目标模型可运行完整 pipeline，不再重复询问是否允许到 execute；调平动作由程序自动逐条执行（不再逐次输入 MOVE），最终任务轨迹仍保留 MOVE 确认；预检 WARN 显示并记录后自动继续，无需输入 CONTINUE。

| 条件 | 当前配置（划掉的旧值已被上方 2026-10-13 更新取代） |
|---|---|
| 授权上限 | execute，允许完整调平→规划→仿真→预检→真机任务轨迹执行；也可根据需要停在 plan/prepare |
| 运动期间采集 | ~~不需要；沿用 `nokov_capture: null`~~ → **已启用**，见上方更新；2026-10-16 起同时采集 ATI 六维力；2026-10-18 起同时录 USB 摄像头 1080p30 |
| 调平时 Nokov | 仍需要测量，用于调平；任务轨迹期间现在也录制 |
| 是否接入新采集适配器 | ~~不需要；当前没有现成 pipeline Nokov 采集适配器，本任务不为此开发或配置~~ → **已接入** `~/ribbon_ws/Nokov/nokov_capture_adapter.py`；2026-10-16 另接入 `~/ribbon_ws/ati/ati_capture_adapter.py`（力）与 `~/ribbon_ws/ati/ati_force_plot.py`（绘图）；2026-10-18 另接入 `~/ribbon_ws/camera/usb_capture_adapter.py`（1080p30 视频） |
| 可选 ribbon_workspace | 当前省略，原因和后续启用条件见 4.6 |
| 名义夹持点 | ~~fer_hand_tcp~~ → **`fer_ribbon_tcp`**（`fer_link8` + 局部 Z 0.058 m）；名义局部偏移零，不声称已实测重合 |

授权适用于用户给定的实验目标，不等于允许任意轨迹、去除保护或修改硬件参数。缺少具体目标时先确定任务内容，不自行挑选示例执行。用户之后缩小范围或要求停止时按新指令执行。

这条 execute 授权已记录供后续操作使用：没有具体新运动目标时不因更新文档而启动设备。

### 6. 如何使用本手册

首次接手先读本文，建立任务、设备和坐标背景；执行具体操作时查第 8 章的接口索引。硬件布局、材料或标定变动时记录用户提供的新事实；文档维护由有权限核对实现的维护者进行。目标模型不能为了更新文档读取 docs 外源码。

可给另一个大模型以下指令：

> 你是 Franka–ribbon 实验的 AI 操作助手。先阅读 `/home/zhaoyunzyq/ribbon_ws/pipeline/docs/RIBBON.md` 的第一部分，再按本次任务查阅同一文件的第二部分。仅通过终端操作，只阅读 docs 内文档和本任务生成的文件；可在任意位置写任务文件。根据需要选择观测、调平、微动、归位、轨迹执行或完整 pipeline，沿用本文已确认的材料轴、名义 TCP 夹持点、运动期间采集（Nokov + ATI 力 + USB 摄像头 1080p30 视频）和 execute 授权，根据具体目标调用，保留交互和检查，并依据本次测量及回执报告结果。我的具体任务是：〈填写目标与执行范围〉。

---

## 第二部分 · API 操作手册

### 7. 公共调用约定

**权限前提：目标模型只能操作终端，只能阅读 `~/ribbon_ws/pipeline/docs/` 内的既有文档/示例；可以在任意位置写文件，并读取本任务过程中生成的文件。** 不能操作 GUI，也不能阅读 docs 外既有源码、现场配置或任意历史记录。完整定义见第 1.1 节。

下列命令可作为程序调用：程序内部加载配置/依赖是正常执行，不授予模型查看这些文件内容的权限。路径出现在参数表里表示可传给 API，不表示可用 cat/rg/Python 读取。读取日志和结果时，只使用本任务生成的精确路径。不能先复制受限文件再读取。

先在终端加载环境：

```bash
cd /home/zhaoyunzyq/ribbon_ws/pipeline
source /opt/ros/humble/setup.bash
source /home/zhaoyunzyq/ribbon_ws/ros/install/setup.bash
```

下面的相对路径均从此工作目录解析；微动示例若切换目录，后续调用需回到该目录。路径占位符必须替换为实际路径。ROS double 参数写 `1.0`，不能用整数 `1` 覆盖。

需要交互的命令用持久 PTY（例如终端工具的 `tty: true`），之后对同一 session 读取提示/输入。不要重复启动仍在运行的任务。各接口确认方式不同，见索引和接口正文。

同一机械臂的 FCI 连接不能被归位、微动、离线执行、只读节点或完整驱动同时占用。先结束自己已知的连接程序；不要强杀不明会话。Nokov 使用独立链路。

独立命令不自动运行 pipeline 的检查链。回执格式各不相同；使用对应接口的成功判据，保存该次输出路径。物理单位与轴方向先按第 1–6 章核对，再填写参数。

### 8. 接口索引

| 需求 | API | 本手册章节 | 运动与确认 |
|---|---|---|---|
| 读机械臂当前状态 | read_franka_state | 9 | 连接 FCI，不发送运动 |
| 查看/记录 ribbon 形状 | nokov_recorder | 10 | 只连接动捕 |
| 分析、测量或调平 ribbon | ribbon_level.py | 11 | analyze/measure 不运动；run 先宽面对齐、再自动逐条执行 |
| 回到保存的规划起点 | home_pose | 12 | 启动即执行，无 Enter 闸门；不是出厂零位；`--from-run` 的小幅起点归位也调用它（15.9） |
| 当前末端附近的小步调整 | cartesian_delta_move | 13 | 默认无输入闸门，连接后即运动；dry-run 只连接读取 |
| 验证/执行已导出的轨迹 | execute_offline | 14 | dry-run 不连接；执行时无额外提示 |
| 完整调平、规划、仿真和可选执行；或复用 plan/prepare 检查点 | run_pipeline.py | 15、15.9 | 正常路径先调平；`--from-run` 跳过调平/规划，改为起点校验；任务执行另有 MOVE |
| 编写 run_pipeline 输入 | 任务 YAML | 16 | 文件格式与静态校验，不是运动入口 |
| 批量提交、排序与自动派发 | robot_gateway（`robot_job`） | 18.3 | 只按序启动；MOVE 提示需用户确认，可远程 confirm 或 attach |

根据当前需要直接选接口；run_pipeline 是其中一个组合接口，不是其他 API 的前置步骤。

远程托管工具（`read_franka_manual`、`robot_pipeline_*` 等）与本章 API 的对应关系见 18.2。批量提交、排序与自动派发见 18.3；队列只负责按序启动，不改变本章任何接口的确认方式。已有任务 YAML 在 tool-chat/tool-agent 里用 `robot_pipeline_list_tasks` → `prepare_robot_pipeline_remote_task` 按路径准备，再交给 `robot_pipeline_submit` 登记，不必为了走工具而改写成 `prepare_robot_pipeline_spec` 的参数。

### 9. read_franka_state：读取机器人状态

```bash
/home/zhaoyunzyq/ribbon_ws/libfranka/build/examples/read_franka_state 172.16.0.3
```

输出 JSON 包含 `q`、`dq`、`O_T_EE` 和 `robot_mode`。关节量单位 rad/rad·s⁻¹，`O_T_EE` 为列主序 4×4 变换，平移在数组索引 12、13、14，单位 m。调用会占用 FCI，不要在其他机器人程序持有连接时并发读取。它不调平、不更新共享起点文件。

### 10. nokov_recorder：观察与记录 ribbon 形状

先看在线资产，确认存在准确名称 `ribbon_1021`：

```bash
cd /home/zhaoyunzyq/ribbon_ws/pipeline
~/ribbon_ws/Nokov/recorder/build/nokov_recorder --mode list --server 10.1.1.198
```

实时查看该侧平面拟合和可见点数量（Ctrl+C 退出）：

```bash
~/ribbon_ws/Nokov/recorder/build/nokov_recorder --mode monitor --server 10.1.1.198 \
  --plane 'ribbon_1021' --up-axis z
```

`monitor` 主要显示数值，不是完整的三维形状查看器。单侧点接近共线时，平面法向可能不稳定；`rms/max_dev` 是到最佳拟合平面的距离，不是到两端连线的下垂量。即使 ribbon 已在一个平面里弯曲，平面残差也可能很小。

采集当前约 2 秒的形状快照，机械臂不动：

```bash
~/ribbon_ws/Nokov/recorder/build/nokov_recorder --mode record --server 10.1.1.198 \
  --plane 'ribbon_1021' --up-axis z --duration 2 \
  --outdir /home/zhaoyunzyq/ribbon_ws/Nokov/data --tag ribbon_y_shape
```

从本次终端 `会话:` 行取得文件前缀。生成 `_markers.csv`、`_plane.csv`、`_rigid_bodies.csv` 和 `_meta.json`。**`--plane` 选择拟合集合，不会把 markers.csv 限制为这一侧**，分析时必须过滤 `source=markerset`、`set_name=ribbon_1021`（当前在线名就是 `ribbon_1021`，2026-10-22 前叫 `ribbon`；两者都不是资产文件名 `ribbon+y`）。坐标单位 mm，为动捕世界系；没有 base 外参时不得直接作为机器人目标。

读取本次 `_markers.csv` 的两端高差、下垂及逐点残差（把路径替换为实际文件）：

```bash
python3 tools/ribbon_level.py --params tools/ribbon_params.yaml \
  analyze /absolute/path/nokov_THIS_RUN_markers.csv --json
```

注意 `--json` 是在文本报告后追加 JSON，并非 stdout 全部为 JSON。退出码 1 也可能仅表示调平判据未达标；不代表采集失败。`analyze` 不发送运动，不修改会话；直接查看当前指标的简写为：

```bash
python3 tools/ribbon_level.py --params tools/ribbon_params.yaml session measure --record
```

后者会更新调平会话测量历史，因此只需查看形状时优先使用 `record` + `analyze`；analyze 的输入必须是本任务生成的记录，不能自行读取 docs 外旧实验数据。

若需要大模型读取该侧真实空间点列，使用下面的标准库脚本，从指定记录取**最后一个至少有两个有效点的帧**，同时报告末尾帧、时刻与有效点数。不得将跨帧点混成瞬时形状：

```bash
python3 - /absolute/path/nokov_THIS_RUN_markers.csv <<'PY'
import csv, json, math, sys
from pathlib import Path
frames = {}
with open(sys.argv[1], newline='') as f:
    for r in csv.DictReader(f):
        if r['source'] != 'markerset' or r['set_name'] != 'ribbon_1021':
            continue
        key = (int(r['wall_unix_ns']), int(r['frame']))
        frame = frames.setdefault(key, {'wall_iso': r['wall_iso'], 'points': []})
        xyz = [float(r[k]) for k in ('x_mm', 'y_mm', 'z_mm')]
        if all(math.isfinite(v) and abs(v) < 1e6 for v in xyz):
            frame['points'].append({'name': r['marker_name'], 'xyz_mm': xyz})
if not frames:
    raise SystemExit('NO_RIBBON_FRAMES')
valid = [k for k,v in frames.items() if len(v['points']) >= 2]
if not valid:
    raise SystemExit('INSUFFICIENT_VISIBLE_POINTS')
k = max(valid)
v = frames[k]
result = {'set_name': 'ribbon_1021', 'frame': k[1],
    'wall_unix_ns': k[0], 'wall_iso': v['wall_iso'],
    'record_last_frame': max(frames)[1],
    'age_to_record_end_ms': (max(frames)[0]-k[0])/1e6,
    'n_visible': len(v['points']), 'points': v['points']}
text = json.dumps(result, ensure_ascii=False, indent=2)
out = Path(sys.argv[1]).with_suffix('.shape.json')
out.write_text(text + '\n')
print(text)
print('SHAPE_JSON=' + str(out.resolve()), file=sys.stderr)
PY
```

上面的命令同时生成同目录 `*.shape.json`。需要图片时，使用该文件绘制有标签的三维散点图（需 Python matplotlib；只处理已保存数据，不连接硬件）：

```bash
python3 - /absolute/path/nokov_THIS_RUN_markers.shape.json <<'PY'
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
p = Path(sys.argv[1])
d = json.loads(p.read_text())
pts = d['points']
fig = plt.figure(figsize=(9, 6))
ax = fig.add_subplot(111, projection='3d')
xs, ys, zs = zip(*(v['xyz_mm'] for v in pts))
ax.scatter(xs, ys, zs, s=40)
for v in pts:
    ax.text(*v['xyz_mm'], v['name'], fontsize=8)
# 三个坐标轴使用相同量程，避免将微小 Z 变形夸大成同等长度。
span = max(max(a)-min(a) for a in (xs, ys, zs)) or 1.0
for values, setter in ((xs, ax.set_xlim), (ys, ax.set_ylim), (zs, ax.set_zlim)):
    center = (max(values)+min(values))/2
    setter(center-span*0.55, center+span*0.55)
ax.set_box_aspect((1, 1, 1))
ax.set(xlabel='Mocap X (mm)', ylabel='Mocap Y (mm)', zlabel='Mocap Z (mm)',
       title=f"ribbon | frame {d['frame']} | {d['wall_iso']} | n={len(pts)}")
out = p.with_suffix('.png')
fig.tight_layout()
fig.savefig(out, dpi=160)
plt.close(fig)
print(out.resolve())
PY
```

目标模型可通过终端生成 PNG 并报告路径，供操作者查看；不能调用图形界面或图片查看工具，也不能宣称自己看过图。通过终端读取本任务生成的 JSON 坐标完成分析。图片标为“该次记录的单帧 marker 形状”，附采集时刻和有效点数。

该点列是有限 marker 采样的单侧形状，不是完整曲面。若画图，使用同一帧的 3D 散点并标注 marker 名；沿材料的真实点序未标定时，不按名称编号随意连线。按 X 排序只适用于已知沿 X 单调展开的状态，折叠/回弯时可能产生错误拓扑。

判断“当前”时核对本次采集时间、`meta.complete`、`frames_written`、实际可见点数量与缺失值。用 `--mode list` 和资产定义核对期望点数（当前在线 `ribbon_1021` 12 点，另有端板 `x1` 4 点、`x0` 3 点），不能把遮挡后剩下的两点当作完整 ribbon。调平算法只分析高差与下垂，不输出完整扭转角；另一侧未被测量时不要声称已获得全宽形状。

### 11. ribbon_level.py：分析、测量与调平

只分析已保存的动捕数据，不连接设备、不运动：

```bash
python3 tools/ribbon_level.py --params tools/ribbon_params.yaml \
  analyze /absolute/path/nokov_THIS_RUN_markers.csv --json
```

`--json` 在文字报告后追加 JSON。退出码 0 表示本次判据达到 done，1 可能只是未达标，2 表示无可用数据等错误；报告不是全宽形状或扭转角测量。原始点列和绘图见第 10 章。

只采集当前测量并更新会话，不发送运动：

```bash
python3 tools/ribbon_level.py --params tools/ribbon_params.yaml session measure --record
```

自动循环测量与自动逐条执行调平（会请求真机运动）：

```bash
python3 tools/ribbon_level.py --params tools/ribbon_params.yaml session run
```

调平动作由程序自动逐条执行，**不再逐次输入 `MOVE`**：先做宽面对齐，再按报告顺序执行松开/升降/拉直。只有动作失败或连续无改善时才暂停；现场问题处理后输入 `RESUME` 重新测量，或 `QUIT` 退出，连续无改善时还可输入 `SKIP` 人工验收成功（其他输入只是继续等待，不会执行动作）。run 成功时读取真机并更新共享 `franka_start_pose.yaml`，不是执行用户的后续边界条件轨迹。返回非零可能发生于部分动作之后，不自动重试。

默认调平参数来自 `tools/ribbon_params.yaml`：marker set 为 `ribbon`、夹爪端为 `max_x`，两端高差容差 2 mm、中间塌陷（所有可见点 z 最大差值）容差 15 mm、连续达标 2 次；单次 Z 修正上限 10 mm，常规拉伸步长 5 mm，累计拉伸上限 40 mm；宽面对齐 `align_ribbon_up: true`，`pull_slow_margin_mm` 7 mm 只是拉直步长分档阈值，不是判据。方向门禁 `axis_ratio_min: 1.5` 只看当前可见点的 x 展布 / y 展布，z 展布不参与（深垂不会因此被拦），等价于允许带子长轴偏离动捕 x 轴约 33.7°；它只拦“marker set 选错 / 带子沿 y 放”，低于下限时 execute 门禁会 abort 并打印 `x 展布 … / y 展布 … = …，低于下限 1.50`；松垂本身不是拒绝理由，误拦时可请维护者下调到 1.2。状态保存在 `tools/state/ribbon_state.json`，跨调用保留，不要为消除限制擅自 `session init --force`。

调平需 Nokov；任务轨迹期间也采集（2026-10-13 起，见 §15.0）。只读查看调平会话：

```bash
python3 tools/ribbon_level.py --params tools/ribbon_params.yaml session status
```


### 12. home_pose：返回保存的规划起点

```bash
ros2 run franka_robot_driver home_pose
```

默认目标为 `/home/zhaoyunzyq/ribbon_ws/ros/src/franka_motion_planner/config/franka_start_pose.yaml` 的关节角。这份文件会在调平成功后更新，所以 **home 是最近保存的规划起点，不是出厂 ready、零关节角或本次运行之前的位置**。程序只读该文件，不更新它。

显式指定目标和较慢时间倍率：

```bash
ros2 run franka_robot_driver home_pose \
  --start-pose /home/zhaoyunzyq/ribbon_ws/ros/src/franka_motion_planner/config/franka_start_pose.yaml \
  --time-scale 5.0 \
  --ros-args -p automatic_error_recovery:=false
```

需要返回本任务某次运行的调平起点时，`--start-pose` 指向那次生成的 `franka_start_pose.yaml`，不要误用后来已更新的共享文件。docs 外既有共享文件可供 home_pose 内部加载，但模型不能直接展开读取；通过程序打印的目标计划核对。

`run_pipeline.py --from-run ... --mode execute` 的起点校验也会调用本命令（15.9）：目标文件是本次目录里由轨迹首点生成的 `planned_start_pose.yaml`，并且只在 guard FK 包络（TCP 1 mm、朝向 2°、X 0.65 mm）通过、操作员输入 `HOME` 后才执行。正常 execute 结束后**不会自动**运行 home_pose；要回到该次运行的起点，手动指定 `pipeline_runs/<run>/franka_start_pose.yaml`（正常执行）或 `pipeline_runs/<run>/planned_start_pose.yaml`（`--from-run` 执行）。`home_pose` 自身仍不做 MoveIt 碰撞检查、没有 ribbon X guard；管线里的包络检查是额外的离线判据，不是 home_pose 自带保护。

| 普通选项 | 默认 / 说明 |
|---|---|
| `--ip` | `172.16.0.3` |
| `--start-pose` | 上述共享起点；缺失时源码有安装目录回退，应检查实际打印目标 |
| `--time-scale` | 3.0，须 ≥1，越大越慢 |
| `--min-duration` | 2.0 s，范围 `[0,600]` |
| `--audit-dir` | `/home/zhaoyunzyq/ribbon_ws/pipeline/execution_logs` |
| `--help` | 只显示帮助 |

本命令是否可执行按本次用户授权判断，不由 pipeline 的 mode 自动授权。程序**不要求交互终端，也不等待 Enter**：连接后读取实测关节、打印七关节起点/目标/差值与时长，检查通过即直接运动，**启动命令本身即构成执行请求**；取消只能用 Ctrl+C。若已在默认 0.01 rad 容差内，直接成功且不运动。

归位是关节空间五次插值运动，**不做 MoveIt 场景检查，也没有 ribbon X guard 检查**。夹着 ribbon 时，即使目标是以前的调平姿态，途中也可能拉扯或越过边界；不能将 home 当作 pipeline 失败后的自动补救。默认 `automatic_error_recovery=true`，上面的显式示例关闭它；碰撞力上下阈值默认 50/40 N、力矩 15/12 N·m，不是 ribbon 允许张力。

退出码 0 表示成功（可能已经到位未运动），1 为失败/取消，普通选项错误为 2。按终端给出的审计目录读取 `home_*/result.json`：核对 `success`、`moved`、`already_home` 和 `message`（`confirmed` 与 `confirmation_required` 恒为 false，本程序不等待确认），不要将返回 0 全部解释成“发生了归位运动”。

### 13. cartesian_delta_move：相对微动

完整语法：

```text
./cartesian_delta_move <robot_ip> <dx_m> <dy_m> <dz_m> [选项]
```

已确认参考装夹中 base +X 从机械臂夹持端指向固定端，+Y/+Z 定义为正宽度/厚度。名义夹持点取 TCP；tool 轴对应及零偏移近似的限制见第 4.4–4.5 节。下面 base +X 微动向固定端移动；实际夹持点精确不动不能仅凭该近似保证。

以下示例目标为 base +X 方向 1 mm，**不是已验证的安全位移**。先只读查看当前与候选目标：

```bash
cd /home/zhaoyunzyq/ribbon_ws/libfranka/build/examples
./cartesian_delta_move 172.16.0.3 0.001 0.0 0.0 --dry-run
```

需要实际执行同一微动时：

```bash
./cartesian_delta_move 172.16.0.3 0.001 0.0 0.0 --duration 2.0
```

独立旋转示例：绕 **base Z** 转 +2°，不是工具 Z：

```bash
./cartesian_delta_move 172.16.0.3 0.0 0.0 0.0 \
  --droll-deg 2.0 --roll-axis z --duration 2.0
```

| 选项 / 行为 | 当前实现 |
|---|---|
| 平移参考 | 相对当前末端，沿 base 轴；与任务 YAML 相对冻结起点的语义不同 |
| 旋转参考 | 仅支持 base x/y/z；`--roll-axis` 默认 x，`--droll-deg` 默认 0°，绝对值不得超过 30° |
| `--duration` | 默认 `max(1 s, 位移长度/0.005 m/s, 转角绝对值/2 deg/s)`；显式值不得小于 0.5 s |
| `--settle` | 默认 0.3 s 末尾驻留 |
| `--max-step-mm` | 默认每轴 30 mm 上限；不是三维位移模长上限，也不是累计拉伸保护 |
| `--align-ribbon-up` | 宽面朝上模式：只做旋转，要求平移与 `--droll-deg` 均为 0；每次最多 2°、误差上限 20°、连接点保持法兰外 58 mm、时长下限 2 s；调平程序在进入升降/拉直之前自动调用 |
| `--force-limit` | 默认力 upper/lower=50/40 N；设置 F 时源码设 upper=F、lower=0.8F；不作为任务常规调节项 |
| `--dry-run` | **会连接真机读取状态**，不发运动、不执行恢复或碰撞阈值设置；不是离线校验 |
| `--no-confirm` | 存在但已无实际作用：`confirm` 默认即为 false，且没有任何选项能打开确认闸门；调平程序仍会传入该参数 |

实现细节影响操作：预览读取 `O_T_EE`，控制实际以首个回调的 `O_T_EE_c` 为命令起点，使用余弦插值。该末端系来自机器人配置，未经标定不要假定与 MoveIt `fer_ribbon_tcp` 完全一致。非 dry-run 会调用自动错误恢复并设置碰撞阈值（普通模式连接后立即设置，`--align-ribbon-up` 模式在打印预览后、运动前设置）。**默认没有确认闸门**：`confirm` 恒为 false，连接读取状态后立即开始运动；取消只能用 Ctrl+C，输入 QUIT 无效。

此工具不回零、不走 MoveIt、不读取 ribbon guard、不维护调平累计拉伸状态。手工微动后，旧规划起点可能失效；下一次 pipeline 应重新调平测量。不要直接用它完成整条边界条件轨迹。

退出码 0/1/2 分别为成功/运行错误/参数错误。完成时打印 `MOTION_START_NS`、`MOTION_DONE_NS`、指令与实测平移；它没有 pipeline 式 JSON 回执，返回成功仍应通过机器人/动捕测量核对实际变化。若权限不满足，按现场已配置方式处理；现有调平程序通过 sudo 调用此二进制，直接命令使用 sudo 时仍保留确认提示，不提升速度或力阈值来绕过错误。

### 14. execute_offline：验证与执行 CSV

输入必须是本任务中选定运行导出的 **CSV**，旁边保留同名 `.ribbon_guard`；不能传 `.csv.yaml`。用实际路径替换下面 `<run_id>`，两次使用同一文件和倍率。

只检查文件、五次插值与保护边界，不连接机器人：

```bash
ros2 run franka_robot_driver execute_offline --ros-args \
  -p 'joint_csv:=/home/zhaoyunzyq/ribbon_ws/pipeline/pipeline_runs/<run_id>/trajectory.csv' \
  -p require_ribbon_guard:=true \
  -p time_scale:=1.0 \
  -p automatic_error_recovery:=false \
  -p dry_run:=true
```

**下条命令没有 Enter/MOVE 闸门，启动即构成执行请求。** 仅在用户已授权此条轨迹执行且现场起点、装夹、空间均已核对后使用：

```bash
ros2 run franka_robot_driver execute_offline --ros-args \
  -p robot_ip:=172.16.0.3 \
  -p 'joint_csv:=/home/zhaoyunzyq/ribbon_ws/pipeline/pipeline_runs/<run_id>/trajectory.csv' \
  -p require_ribbon_guard:=true \
  -p time_scale:=1.0 \
  -p start_tolerance:=0.01 \
  -p automatic_error_recovery:=false \
  -p dry_run:=false
```

`<run_id>` 是文档占位符，**必须替换后再交给 shell**，不可原样执行。示例将整个参数加引号，以避免尖括号被 shell 解释为重定向。

时间倍率 `time_scale ≥1`，2.0 表示时间拉长两倍；缩放后最长 600 s。ROS double 参数必须写小数（`1.0`，不能写 `1`）。节点默认 `dry_run=false`、`automatic_error_recovery=true`；上述命令显式关闭自动恢复，与 pipeline 默认适配器一致。未传 `gripper_csv` 时不发送夹爪事件。

该入口不重新调平、不规划、不仿真、不启动 Nokov、不检查 MoveIt 场景，不自动接近轨迹首点；起点最大关节误差超过 `start_tolerance`（默认 0.01 rad，实现允许范围 (0, 0.05]）会拒绝。`dry_run=true` 通过不能证明实测起点符合要求。节点会设置默认碰撞力 upper/lower=50/40 N、力矩=15/12 N·m；不要将保护触发简单理解为阈值太低。

成功退出码 0，失败/取消 1；参数构造错误可能没有回执。按打印路径读取 `execution_logs/offline_*/result.json`，执行成功须 `success=true` 且 `dry_run=false`、`mock=false`、`ribbon_guard=true`。保留 `samples.csv` 和输入副本。独立执行不会更新原 pipeline 的完成状态，不能把旧 pipeline 回执当作本次执行回执。

### 15. run_pipeline.py：组合流程

**用途：** 从任务 YAML 出发，依次处理起点、规划、仿真、预检，并按 mode 决定是否执行任务轨迹；`--from-run` 可复用已完成的 plan/prepare（15.9）。不是只读接口：正常路径下硬件可用且终端可交互时，**`plan`、`prepare`、`execute` 都会先调平，可能移动真机**；`--from-run` 跳过调平/规划，但会在 execute 前做起点校验，并可能用 `home_pose` 归位。`plan`/`prepare` 在机械臂/动捕连不上或非交互终端时降级为现有默认起点，不运动（15.1）。只检查 YAML 请用本节静态校验命令。

#### 15.0 已确认的调用条件

**当前用户授权到 execute，且运动期间采集已启用。** 对用户指定的具体实验目标，可直接选择 `--mode execute`；不必重复询问同一权限。`tools/pipeline_adapters.yaml` 的 `nokov_capture` 指向 `~/ribbon_ws/Nokov/nokov_capture_adapter.py`，整段真机轨迹期间持续记录 ribbon markerset，成功结果为 `executed_and_captured`。正常 `execute` 调平阶段仍需要 Nokov 测量；`--from-run` 跳过调平，因此不读取调平阶段的 Nokov 数据，但执行期间的 `nokov_capture` 仍按配置启用。`plan`/`prepare` 在 Nokov 或机械臂不可用时可以跳过调平（见 15.1）。

> **2026-10-13 更新**：本段此前为“运动期间不采集、沿用 `nokov_capture: null`、不配置采集适配器”。用户明确要求记录运动过程中的 ribbon 点后改为默认启用；把 `nokov_capture` 置回 `null` 即恢复不采集（成功结果变回 `executed_without_capture`）。授权上限、最终 MOVE、保护与边界检查均不变；调平动作改为自动逐条执行，不再逐次确认。

> **2026-10-16 更新（力采集）**：按用户要求，execute 模式在动捕启动的**同一时刻**再启动一路
> ATI Mini45 六维力测量（`tools/pipeline_adapters.yaml` 的 `ati_capture` → `~/ribbon_ws/ati/ati_capture_adapter.py`，
> 默认设备 `172.16.0.5:49152`）。它默认开启，且与动捕**同等严格**：收不到力数据、中途断流或
> 未覆盖运动时段都会以 `FORCE_*` 错误码中止，不会在缺数据时继续真机运动；置
> `ati_capture: null` 即关闭。运动结束后自动生成力数据图 `force/force.png`（可用
> `--no-force-plot` 关闭；绘图失败只记 WARN、不影响任何判据）。结果键为 `result.json` 的
> `force_capture` / `force_plot_preview`（或 `force_plot_warning`）。授权、MOVE 确认、
> 保护与边界检查均不变；调平阶段不使用力传感器。现场前提、标定退化与首次上机结果见 15.8。

> **2026-10-18 更新（USB 摄像头）**：按用户要求，execute 模式在动捕/力采集启动的**同一时刻**
> 再启动一路 USB 摄像头录像（`tools/pipeline_adapters.yaml` 的 `usb_capture` →
> `~/ribbon_ws/camera/usb_capture_adapter.py`）。默认 1920x1080 @ 30 fps，运动结束后
> 随停止文件一起收尾。它默认开启且与动捕/力采集**同等严格**：打不开、中途断流或未覆盖
> 运动时段都会以 `CAMERA_*` 错误码中止，不会在缺视频时继续真机运动；置
> `usb_capture: null` 即关闭。结果键为 `result.json` 的 `camera_capture`，产物为
> `usb_camera_<run_id>.mp4`、`_frames.csv` 与 `_meta.json`。授权、MOVE 确认、保护与边界
> 检查均不变；调平阶段不使用摄像头。详见 15.10。

- 任务 YAML 使用本文约定的 base 轴向；名义夹持点为 fer_ribbon_tcp，省略可选 ribbon_workspace，保留 X guard。
- 调平动作（宽面对齐、松开、升降、拉直）由程序自动逐条执行，不再逐次输入 `MOVE`；最终执行 MOVE 仍按当前提示处理，不预填确认词。预检 WARN 显示并记录后自动继续，无需输入 CONTINUE。
- execute 授权不指定运动内容：没有具体轨迹目标时不自行运行示例。
- 目标模型只能使用终端。仿真阶段默认无 Gazebo 界面；需要现场看画面时由用户加 `--gui`，仿真录像默认开启，可用 `--no-video` 关闭（路径与回执字段见 15.6；视频不自动升级证据等级）。视觉核对由现场操作者/用户完成，模型只读本次 summary/日志/回执，不宣称看过画面。
- 若用户后续要求停止录制或缩小授权，按新指令更新条件。自行在别处启动的独立 Nokov 录制不会产生 pipeline 的同步采集回执；只有经 `nokov_capture` 适配器启动的采集才写入本次 run 的 `capture_result.json`。

#### 15.1 模式与生命周期

```text
正常路径：
validate → ribbon_level → plan
                           ├─ plan: 结束
                           └─ simulate → preflight
                                           ├─ prepare: 结束
                                           └─ robot_prepare → execution_confirm
                                                → robot_execute → 结束

--from-run <plan/prepare 运行> 路径：
resume_validate → [simulation_reuse | simulate] → preflight
                ├─ prepare: 写 prepare 检查点，结束
                └─ execute: start_check → robot_prepare
                              → execution_confirm → robot_execute → 结束
```

`--from-run` 是 2026-10-18 新增的复用路径（详见 15.9）：它跳过 `validate`/`ribbon_level`/`plan`，
在新运行目录里校验并复制源运行的 task/trajectory/guard/起点，按源 level 复用仿真（源为 `plan` 时补跑；
预检仍重跑），execute 时在 `robot_prepare` 前增加 `start_check`。`--from-run` 只能配 `--mode prepare/execute`；
不能与 `--task`、`--scene`、`--skip-leveling` 同用。源运行目录保持不变。
SSH 任务网关封装 `prepare`/`execute` 复用（`submit_resume`，见 18.2）；`execute --from-run` 进入普通队列，运行中的提示用 `robot_pipeline_confirm` 远程确认或 attach 处理。

配置 `nokov_capture` 时，最后执行部分另有 `capture_start` 和 `capture_finish`；配置
`ati_capture` 时另有 `force_start` 和 `force_finish`；配置 `usb_capture` 时另有
`camera_start` 和 `camera_finish`。各路采集都在 `execution_confirm` 之后、
`robot_execute` 之前启动（因此是同时开启），在运动结束后各自收尾。
任一阶段失败均停止后续步骤；pipeline 不自动重试。

`simulate` 阶段默认无 Gazebo 界面（只起物理服务器）；`--gui` 默认关闭，`--video` 默认开启。录像本身不参与通过判据；但图形环境故障或渲染过慢可能使仿真启动失败/超时，不能保证开启 GUI 不影响流程。

| `--mode` | 调平可能移动真机 | 执行任务轨迹 | 成功 outcome |
|---|---|---|---|
| `plan` | 硬件可用且交互时是；连不上时降级为默认起点，不运动 | 否 | `planned` |
| `prepare`（默认） | 硬件可用且交互时是；连不上时降级为默认起点，不运动 | 否 | `offline_checks_passed` |
| `execute`（不带 `--from-run`） | 是，始终要求调平 | 是，需最终确认 | 默认（动捕+力采集+USB 摄像头都开）`executed_and_captured`；所有采集通道都置 `null` 才为 `executed_without_capture` |
| `execute --from-run` | 否，跳过调平/规划；`start_check` 在确认 `HOME` 后可用 `home_pose` 归位（15.9） | 是，需最终确认 | 同上；`result.json` 另有 `resume_source` / `start_state_check` |

注意：`prepare` 模式不运行名为 `robot_prepare` 的阶段。真机准备适配器只在 `execute` 模式调用；
`--from-run --mode prepare` 只补仿真/预检并写 prepare 检查点，不调用 `robot_prepare`。

`ribbon_level` 阶段在 `plan`/`prepare` 下先做只读探测：`read_franka_state` 读机械臂、`nokov_recorder --mode list` 连动捕。两者都可用且 stdin 是交互终端时才进入真机调平；任一不可用、或 stdin 不是终端时，跳过调平，把 `--ribbon-params` 中 `planner_start_pose_file` 的现有默认起点复制为本次 `default_start_pose.yaml` 继续。该路径不运动、不改写共享起点、不做世界系标定；`result.json` 记 `initial_state_source=default_start_pose_fallback`、`calibration`、`leveling_probe`，`world_base_calibration.status=skipped`，`ribbon_video_warning.status=skipped`。`--skip-leveling` 可让 `plan`/`prepare` 不探测硬件直接走这条路径；正常 `execute` 会拒绝该参数，`--from-run` 也不接受它（复用本身即跳过调平）。

正常路径每次调用都新建 `pipeline_runs/<时间戳>_<标识>/`，复制任务，完成调平后读取真机关节状态，生成本次 `franka_start_pose.yaml`，再将本次任务副本的起点改为该快照；降级运行则生成 `default_start_pose.yaml` 并把任务副本指向它。原始任务 YAML 不被改写。`--from-run` 同样新建目录，但不再调平或规划：它复制源运行的 `trajectory.csv`/`.csv.yaml`/`.ribbon_guard`，生成 `planned_start_pose.yaml`（trajectory 首点）和 `source_start_pose.yaml`，并把 task 副本的起点指向 `planned_start_pose.yaml`；源运行目录保持不变。

从 2026-10-18 起有 `--from-run`，但仍**没有** `--yes` 或跳过最终 `MOVE` 的接口；也不跳过
`preflight`、`robot_prepare` 或采集。不带 `--from-run` 时，`prepare` → `execute` 仍是两次独立运行，
会重新调平、重新规划；这与“复用检查点”是两条不同路径。

#### 15.2 创建与校验输入

```bash
cd /home/zhaoyunzyq/ribbon_ws/pipeline
source /opt/ros/humble/setup.bash
source /home/zhaoyunzyq/ribbon_ws/ros/install/setup.bash
mkdir -p ~/ribbon_ws/trajectories
cp -n docs/examples/ribbon_boundary_example.yaml ~/ribbon_ws/trajectories/my_ribbon_task.yaml
```

编辑本任务创建的 `~/ribbon_ws/trajectories/my_ribbon_task.yaml` 为用户实际需求；可以改用任意输出位置。若目标文件已存在但不是本任务生成的，换一个新文件名，不读取或覆盖旧文件。`cp -n` 不覆盖已有文件。下面的校验是已文档化的函数调用，模块内部加载起点文件，不连接设备、不启动 ROS 节点；不得额外打印模块源码或既有起点文件内容：

```bash
PYTHONPATH=/home/zhaoyunzyq/ribbon_ws/ros/src/franka_motion_planner python3 - <<'PY'
from pathlib import Path
from franka_motion_planner.task_config import load_task
p = Path('/home/zhaoyunzyq/ribbon_ws/trajectories/my_ribbon_task.yaml')
d = load_task(p)
assert d['ribbon_task'] is True, '本操作文档要求显式 ribbon_task: true'
print('YAML_VALID', 'waypoints=', len(d['motions']))
PY
```

如指定 scene，将 `load_task(p)` 改为 `load_task(p, '/绝对路径/scene.yaml')`。上面的 `load_task(p)` 会要求 `start_state` 带 `ribbon_mount: flange_58mm_v3`；pipeline 的首次校验允许暂缺，但调平后会强制。校验通过仅证明配置可解析，不能证明可达或可执行。pipeline 本身也会再校验一次。

#### 15.2.1 编写 YAML 必须完成的 prepare 验证（2026-10-18）

**完成标准：供机械臂执行的 YAML，必须对最终完整文件通过 prepare，才能报告“撰写并完成离线验证”。**
load_task 的 YAML_VALID 只证明输入可解析；表格数值正确、目标点X偏移非负、
材料端距满足几何约束，都不能替代机械臂逆运动学、连续路径、关节限制、碰撞模型、仿真和预检。
不能只写一句“未经可达性验证”就把可执行路径的撰写任务视为完成。

按以下顺序操作：

1. 先审查实验条件和接口能力，换算坐标与增量角度，明确初始端距/端角、材料长度和TCP参考。
   不从相对位移幅值推断机械臂可达，不把材料球形外包络当作机械臂工作空间。
   若接口不支持恒角速度、连续过点或条件停止，明确标为几何参考/功能未实现；
   prepare 通过也不能证明这些功能已经实现。
2. 静态校验通过后，默认先运行下面的离线 prepare。--skip-leveling 明确使用现有默认起点，
   不探测硬件、不进行真机调平；仍必须完成规划、仿真、预检，不只停在 plan。
   不能伪造起点、绕开缺失快照或擅自改写共享默认起点。
3. 检查本次运行的 result.json、planning.log、仿真摘要和 preflight.json。
   必须为 mode=prepare、outcome=offline_checks_passed，且各必需阶段成功、无预检 FAIL。
   不能只凭进程返回0、生成CSV、部分失败预览或录像存在判断成功。
   WARN 必须逐项说明；保留未解决项，不改报OK，不因程序自动继续就略去。
4. 批量文件须逐份验证，不能用同一组中的一份代表所有参数切片。验证要覆盖全部制备段、
   加载段、停留和末尾回程；单个目标点有逆解不代表整段linear可行。
   验证后再修改任何运动字段（包括追加直线回程）都必须重新验证最终文件。
5. 失败时保留失败回执，区分不可达/路径失败和环境、超时、仿真或起点缺失等原因。
   不在没有诊断的情况下重复运行；不把所有失败一概归因于机械臂范围。
   在用户已允许的范围内调整并重验；需要改变固定端距、角度、扫描范围、起点/装夹等实验条件时，
   先给出具体失败位置与可选调整，再由用户决定，不能静默缩小后仍声称符合原表。
   不以linear改free、降低guard/碰撞或预检阈值、删除失败段的方式制造“通过”。

默认离线验证命令（从远端工作区执行，将task替换为本任务最终YAML的绝对路径）：

```bash
cd /home/zhaoyunzyq/ribbon_ws/pipeline
source /opt/ros/humble/setup.bash
source /home/zhaoyunzyq/ribbon_ws/ros/install/setup.bash
python3 tools/run_pipeline.py \
  --task /home/zhaoyunzyq/ribbon_ws/trajectories/my_ribbon_task.yaml \
  --mode prepare --skip-leveling
```

**起点证据必须分开报告。** 使用--skip-leveling或自动降级时，
result.json的initial_state_source为default_start_pose_fallback；
通过只能表述为“基于默认起点，完整离线检查通过”，不能表述为“已验证当前真机起点可执行”。
若任务要求针对当前实际装夹/姿态验证，且现场运动已在用户授权范围内，
再运行不带--skip-leveling的prepare，并核对回执确实使用本次实测调平起点而非自动降级。
普通prepare在硬件可用、交互终端下会先移动真机调平；没有相应授权时不能为完成文件撰写而启动调平。
prepare不执行完整任务轨迹，也不包含execute中的robot_prepare阶段。

**验证与最终文件绑定。** 在旁置README或validation.json中记录每份YAML的最终文件SHA256、
对应pipeline_runs绝对路径、mode、outcome、initial_state_source、各必需阶段结果、
preflight告警，以及是否修改了原始实验范围。pipeline会替换冻结任务副本的起点字段，
原输入文件哈希与运行目录task.yaml哈希可能不同，须注明二者用途并保留对应关系，不能直接要求二者相等。
这些记录放在旁置文件，不在任务YAML中新增解析器不支持的字段。

交付时明确区分：
- **未验证草稿**：未运行或未通过完整prepare，不能作为已完成的可执行路径。
- **默认起点离线通过**：完整prepare通过，但起点来自默认快照。
- **本次调平起点离线通过**：完整prepare通过，且回执证实使用本次实测调平起点。

这些状态都不等于真机任务成功或材料安全已验证。固定端、夹具、可变形ribbon的碰撞与受力
不一定包含在当前模型中；现场仍须核对。默认（不带 `--from-run`）的 execute 会重新调平、重新规划和检查；
`--from-run execute` 复用同一条轨迹，但会先做起点校验（15.9），先前 prepare 通过仍不能保证新起点或现场安全。
不要为了交付 YAML 自动升级到 execute。

#### 15.3 调用命令

只需一次完整调平→规划→仿真→真机执行时，直接使用 execute，不必先分别运行其他模式：

```bash
python3 tools/run_pipeline.py \
  --task /home/zhaoyunzyq/ribbon_ws/trajectories/my_ribbon_task.yaml \
  --mode execute
```

若用户只授权调平和规划，使用 `--mode plan`；若还需仿真与预检但不执行目标轨迹，使用 `--mode prepare`。硬件可用且交互运行时两者都有调平运动；设备不可用时可显式离线：

```bash
python3 tools/run_pipeline.py \
  --task /home/zhaoyunzyq/ribbon_ws/trajectories/my_ribbon_task.yaml \
  --mode plan --skip-leveling
```

先 prepare，稍后只补执行（2026-10-18 新增，详见 15.9）：

```bash
# 先调平 → 规划 → 仿真 → 预检，并写出 checkpoint.json
python3 tools/run_pipeline.py \
  --task /home/zhaoyunzyq/ribbon_ws/trajectories/my_ribbon_task.yaml \
  --mode prepare

# 稍后复用上面的 plan/prepare，只做起点校验 + robot_prepare + MOVE + 执行 + 采集
python3 tools/run_pipeline.py \
  --from-run /home/zhaoyunzyq/ribbon_ws/pipeline/pipeline_runs/<prepare_run_id> \
  --mode execute
```

`--from-run` 接受运行目录、该目录的 `result.json` 或 `checkpoint.json`；它**新建**一个运行目录，
源目录不动。`--from-run` 不能再给 `--task`（任务来自源运行），也不能配 `--scene`、`--skip-leveling`
或 `--mode plan`。源是 `plan` 时会在 execute 时补仿真；源是 `prepare` 时复用仿真，但**预检**、
`robot_prepare`、最终 `MOVE` 和采集都不跳过。只想先 plan、稍后再补仿真/预检，可以：

```bash
python3 tools/run_pipeline.py --task /abs/path/task.yaml --mode plan
python3 tools/run_pipeline.py --from-run pipeline_runs/<plan_run_id> --mode prepare
```

`--skip-leveling` 只适用于 `plan`/`prepare`，使用 `--ribbon-params` 里 `planner_start_pose_file` 的现有默认起点；正常 `execute` 必须调平，`--from-run` 也不接受它（复用本身即跳过调平）。若终端不是 PTY，`plan`/`prepare` 会自动走同一条默认起点路径并在 `result.json` 标记；pipeline 仍要求交互式终端（PTY）；网关的 tmux 会话提供该 PTY，可用 `robot_pipeline_confirm` 远程发送合法答案，也可 attach 输入。`--from-run execute` 的 `HOME`/`RELEVEL`/`QUIT` 同样走这一确认通道。

仿真默认不开 Gazebo 界面，默认录制相机视频；任务采集结束后默认生成 ribbon 交互 HTML（`videos/ribbon_viewer.html`），两个 MP4 默认不生成。需要现场图形窗口时才加 `--gui`；关闭录像用 `--no-video` / `--no-ribbon-video`；需要两个 MP4 时加 `--ribbon-videos`。授权、预检和 `MOVE` 确认保持原流程（可用 `robot_pipeline_confirm` 远程回答），GUI 仍需远端可用图形环境：

```bash
python3 tools/run_pipeline.py \
  --task /home/zhaoyunzyq/ribbon_ws/trajectories/my_ribbon_task.yaml \
  --mode execute --video
```

大模型的终端工具必须支持持久 PTY/交互会话（例如 `exec_command` 的 `tty: true`，之后对同一 session 读取输出/输入）。不要用非交互后台作业代替。长任务保持同一会话，等待当前输出，不要重复启动入口。

#### 15.4 处理提示

| 提示 | 操作 |
|---|---|
| 调平报告后自动执行动作 | 宽面对齐与随后的松开/升降/拉直会立即自动执行；核对报告里的方向、位移、marker 与当前现场，异常时 Ctrl+C 或按提示 `QUIT` |
| `RESUME` / `SKIP` / `QUIT` | 异常、响应不足或取消后暂停；现场问题解决才 `RESUME`，连续无改善且人工确认当前结果可接受可 `SKIP`（记为人工验收成功并保存规划起点），否则 `QUIT`。重新测量不代表此前没有移动 |
| 预检 `WARN` 自动继续 | 告警显示并保留在 `preflight.json`，自动继续记录写入 `result.json`；不可把 WARN 报成 OK |
| 仿真结束后的最终 `MOVE` | 核对本次路径、实测起点、执行限制和是否采集，再确认整条任务轨迹。有界面时（`--gui`）窗口停在末态可看；无界面时看 `simulation/report.txt`、`actual.csv`，以及 `--video` 产出的 `simulation/gazebo_review.mp4` |
| `--from-run` 的 `HOME` / `RELEVEL` / `QUIT` | 起点差在 0.008–0.20 rad 且 guard FK 包络通过时出现。`HOME` 会用 `home_pose` 把机械臂归位到本次轨迹首点，是真实运动；`RELEVEL` 退出并打印重新调平+规划的命令；`QUIT` 取消。较大漂移或路径不安全时不会询问，直接以 `START_STATE_DRIFT` 退出 |
| `--from-run` 的仿真复用提示 | 源运行有可用仿真时不会重新启动 Gazebo，终端会打印源 summary/actual 路径；本次预检仍重新运行。没有可用仿真时打印原因并重跑仿真 |
| `--on-start-drift abort` | 不询问 `HOME`，超过直执行阈值直接退出；用于完全不允许自动归位的场景 |

调平参数、会话状态与单独调用方式见第 11 章。调平与任务轨迹期间都使用 Nokov；任务轨迹采集由 `nokov_capture` 适配器负责，见 §15.0。`--from-run` 的起点校验/归位细节见 15.9。

需要取消时使用终端 Ctrl+C；pipeline 尝试清理本次进程并保存结果。进程退出或信号返回不能证明机器人已物理停止；现场紧急停止使用现场既定方式，之后查状态再决定下一步。

#### 15.5 参数

| 参数 | 默认值 / 约束 |
|---|---|
| `--task` | 正常路径必填，任务 YAML；使用 `--from-run` 时省略（任务来自源运行） |
| `--mode` | `prepare`；可选 plan / prepare / execute |
| `--from-run` | 不指定；复用一次已完成的 plan/prepare 运行（目录、`result.json` 或 `checkpoint.json`），只配 prepare/execute，详见 15.9 |
| `--on-start-drift` | `ask`；`ask` 在 0.008–0.20 rad 且路径包络通过时询问 HOME/RELEVEL/QUIT，`abort` 直接退出、不询问 |
| `--start-ready-tolerance` | `0.008` rad；当前关节与轨迹首点差在此内直接执行，范围 `(0,0.01]`（执行器硬限制 0.01） |
| `--start-correction-limit` | `0.20` rad；超过直执行阈值后，只有在此内才尝试 `home_pose` 归位；不得小于 `--start-ready-tolerance` |
| `--correction-path-tolerance-mm` | `1.0` mm；归位路径最大 TCP 偏离，范围 `(0,5]` |
| `--correction-orientation-tolerance-deg` | `2.0`°；归位路径最大 TCP 朝向偏离，范围 `(0,10]` |
| `--correction-time-scale` / `--correction-min-duration` / `--correction-timeout` | `5.0` / `5.0 s` / `600 s`；`home_pose` 归位速度、最小时长与进程超时 |
| `--gui` | 不指定（默认无头：只起物理服务器，不启动 Gazebo 界面） |
| `--video` / `--no-video` | 默认开启；录制 `simulate` 的整段 Gazebo 相机回放（含引导段），输出 `simulation/gazebo_review.mp4`；`--no-video` 关闭，录像不参与通过判据 |
| `--ribbon-video` / `--no-ribbon-video` | 默认开启；本任务 Nokov 采集数据生成 `videos/ribbon_viewer.html`（交互 HTML）和质量回执；`--no-ribbon-video` 关闭整段 ribbon 后处理。无采集数据时报告不可用，不伪造产物 |
| `--ribbon-videos` / `--no-ribbon-videos` | 默认关闭；仅在 `--ribbon-video` 开启时有效。额外渲染 `videos/ribbon_fit.mp4`（标注）与 `videos/ribbon_only.mp4`（纯带子）。耗时约与运动时长成正比，85 s 运动约 3 分钟；默认只出 HTML 就是为了避免这段等待 |
| `--force-plot` / `--no-force-plot` | 默认开启；运动结束后把本次 ATI 力数据画成 `force/force.png`（4 行 × 2 列共 8 个面板）并写 `force/force_plot.json`；`--no-force-plot` 关闭。只影响旁证图，绘图失败只记 WARN，不改变任何判据 |
| `--scene` | 不指定；可选场景 YAML；不能与 `--from-run` 同用 |
| `--skip-leveling` | 不指定；仅 plan/prepare。跳过调平与硬件探测，使用 `--ribbon-params` 中 `planner_start_pose_file` 的现有默认起点；正常 execute 会拒绝该参数，`--from-run` 也不接受它 |
| `--ribbon-params` | `/home/zhaoyunzyq/ribbon_ws/pipeline/tools/ribbon_params.yaml`；`plan`/`prepare` 的默认起点也取自其中的 `planner_start_pose_file` |
| `--config` | `/home/zhaoyunzyq/ribbon_ws/pipeline/tools/pipeline_adapters.yaml`，设备适配配置 |
| `--output-root` | `/home/zhaoyunzyq/ribbon_ws/pipeline/pipeline_runs` |
| `--planning-domain` | 81 |
| `--simulation-domain` | 82；两个域必须不同，均为整数 `[0,101]` |
| `--planning-timeout` | 1800 s，正有限数 |
| `--simulation-timeout` | 1200 s，必须 >200 s |
| `--execution-timeout` | 900 s，正有限数；是执行阶段超时，不是全流程超时 |

`--from-run` 与 `--task`、`--scene`、`--skip-leveling` 互斥，也不支持 `--mode plan`；它只跳过调平/规划/仿真（按源 level），不跳过预检、`robot_prepare`、`MOVE` 或采集。

运行时间包含规划后的轨迹停留。长时间 hold 应相应考虑仿真与执行超时，但增加超时不能解决轨迹约束失败。

仿真阶段**默认无 Gazebo 界面**（只起物理服务器），因此不要求显示器；没有 `--headless` 参数——无头就是默认，开界面用 `--gui`。录像默认开启，关闭用 `--no-video`，它只是给人看的旁证：缺失或失败只写告警（`result.json` 的 `simulation_video_warning`），不会产生 `SIMULATION_*`。相机渲染与 1 kHz 控制回路在同一仿真进程里，分辨率×帧率过高会把仿真拖慢到回放超时（表现为 `SIMULATION_FAILED`），默认值已留有余量；不要为“看得更清楚”要求现场调高。

适配配置与任务 YAML 分离。默认 `robot_prepare`、`robot_execute` 调用 `tools/pipeline_offline_adapter.py`，最终通过 `franka_robot_driver/execute_offline` 执行；`nokov_capture` 指向 `~/ribbon_ws/Nokov/nokov_capture_adapter.py`，整段轨迹期间采集 ribbon markerset；`ati_capture` 指向 `~/ribbon_ws/ati/ati_capture_adapter.py`，同一时段记录 ATI Mini45 六维力/力矩；`usb_capture` 指向 `~/ribbon_ws/camera/usb_capture_adapter.py`，同一时段录 1920x1080@30 视频。机器人 IP 从 ribbon 参数读取，目前为 `172.16.0.3`；Nokov server 当前为 `10.1.1.198`；力传感器为 `172.16.0.5:49152`（写在该适配配置的 `--ip` 里）；摄像头默认自动选择非内置 USB 设备（本机 `/dev/video2 "1080P USB Camera"`）。这些是现场配置，不应随任务位姿修改。

`nokov_capture` / `ati_capture` / `usb_capture` 不能只填 `true`：它们必须是满足采集回执协议的命令参数数组，默认值为已核对的适配器调用。要改变采集行为（换 markerset、改设备 IP、换摄像头/分辨率、关闭某一路）由维护者修改该适配配置：置为 `null` 即关闭那一路，所有通道都关闭时成功结果才是 `executed_without_capture`。协议可查 docs 内的 [PIPELINE.md](PIPELINE.md)，目标模型不得自行读取 run_pipeline 源码或既有适配配置；有实现差异时请维护者提供已核对的说明/适配器。

#### 15.6 返回值与产物

正常进入运行流程后，终端最后输出一行 JSON，形如：

```json
{"status":"succeeded","result":"/home/zhaoyunzyq/ribbon_ws/pipeline/pipeline_runs/<run_id>/result.json","error":null}
```

用该返回的精确路径识别本次运行，不按“最近一个目录”猜测。退出码：0 成功，1 失败，130 中断；命令行参数错误可由 argparse 直接返回 2，尚未创建运行目录。

`plan`/`prepare` 降级运行时，`result.json` 另有 `initial_state_source=default_start_pose_fallback`、
`calibration`（含 `status=skipped_default_start_pose`、`reason`、起点来源/哈希/时间）、
`leveling_probe`（机器人/动捕探测结果）、`world_base_calibration.status=skipped`、
`ribbon_video_warning.status=skipped`。读到这些字段时，本次起点不是实测姿态，不得据此声称机器人已在起点或具备上机条件。

| 产物 | 用途 |
|---|---|
| `result.json` | schema_version=1；status、mode、outcome、阶段状态、错误、产物绝对路径、哈希；`--from-run` 另有 `resume_source` / `start_state_check` / `simulation_source` 等字段 |
| `motion_summary.txt` | 本次运行的“人话走法”：合并连续相同动作后逐条列出（如“沿 base +X 走 35 cm”“原地绕 base +Y 轴转 +5° ×6 次”），并给出结果/失败原因；只读 `task.yaml`、`trajectory.csv.yaml`、`result.json`，不新增判据。`result.json` 的 `motion_summary` 字段记录文件名 |
| `task.yaml` | 本次冻结任务副本，起点已替换 |
| `checkpoint.json` | plan/simulate/prepare 成功后写出的可复用检查点；execute 运行不写。记录 task/trajectory/guard/起点/仿真/预检的路径与 SHA256 |
| `franka_start_pose.yaml` | 正常调平路径的本次实测起点；`--from-run` 运行没有这份实测起点 |
| `default_start_pose.yaml` | 降级运行时复制的现有默认起点（`initial_state_source=default_start_pose_fallback`） |
| `planned_start_pose.yaml` / `source_start_pose.yaml` | 仅 `--from-run`：`planned_start_pose.yaml` 由轨迹首点生成，是起点归位的目标；`source_start_pose.yaml` 是源运行起点文件的副本，仅供追溯 |
| `start_correction/home_*/result.json` | 仅发生 `HOME` 归位时：`home_pose` 的审计回执、实测起点/目标和逐关节差值；`start_correction.log` 为进程日志 |
| `trajectory.csv` | 关节轨迹；首列时间 s，其余七关节角 rad |
| `trajectory.csv.yaml` | 轨迹和段元数据、目标朝向、时间、约束结果 |
| `trajectory.csv.ribbon_guard` | 与 CSV 哈希绑定的边界/运动学保护文件，必须和 CSV 保留在一起 |
| `planning.log` | 规划过程、成功标志或失败诊断 |
| `trajectory.failed_preview.yaml` | 部分失败可能生成的预览；不可执行，不是成功轨迹 |
| `simulation/summary.json`、`actual.csv`、`commanded.csv` | 仿真摘要与记录，后两者在 simulation 目录下；`summary.json` 的 `video` 字段记录录像状态 |
| `simulation/gazebo_review.mp4` | 默认启用、可用 `--no-video` 关闭的原生 Gazebo 相机录像（整段回放含引导段）；成功时 `result.json` 有 `simulation_video`，失败时只有 `simulation_video_warning` |
| `videos/ribbon_viewer.html`、`ribbon_fit_diagnostics.json`、`ribbon.json` | 默认生成的本任务 marker 重建交互 HTML（零依赖、离线可用）及逐帧诊断/回执；`result.json` 用 `ribbon_video_preview` / `ribbon_video_warning` 报告，默认 `ribbon_video_preview.path` 指向 HTML |
| `videos/ribbon_fit.mp4`、`videos/ribbon_only.mp4` | 可选；仅在 `--ribbon-videos`（或网关 `render_videos` 补录）时生成。标注视频含 marker/虚线/曲面，纯带子视频只有曲面；不参与判据 |
| `preflight.json` | 预检原始 OK/WARN/FAIL 报告 |
| `robot_ready.json`、`robot_prepare_state.json`、`robot_prepare_boundary.json` | execute 模式的准备证据及实测 X 余量 |
| `robot_result.json`、`offline_execute_*/offline_*/result.json` | 默认执行适配器及原生执行回执 |
| `ati_force_<run_id>.csv`、`force_result.json`、`force_status.json` | 运动期间的 ATI 六维力原始记录（`wall_unix_ns` 与 Nokov CSV 同源，可离线对齐）及采集回执；标定不可用时记为 `calibrated=false`，各列只有原始 counts（见 15.8） |
| `usb_camera_<run_id>.mp4`、`usb_camera_<run_id>_frames.csv`、`usb_camera_<run_id>_meta.json`、`camera_result.json`、`camera_status.json` | 运动期间的 USB 摄像头视频（默认 1920x1080@30 H.264）、逐帧时间戳/模式信息和采集回执；`frame_index` 与视频帧号一一对应，`wall_unix_ns` 与 Nokov/ATI 同源（见 15.10） |
| `force/force.png`、`force/force_plot.json` | 运动结束后自动生成的力数据图（Fx/Fy/Fz/Tx/Ty/Tz 与 \|F\|/\|T\| 共 8 个面板，运动窗口用底色标出）及绘图回执；`result.json` 用 `force_plot_preview` / `force_plot_warning` 报告，`--no-force-plot` 可关闭 |

`motion_summary.txt` 由 `run_pipeline.py` 收尾时写入本次运行根目录；`franka_api.py` 写 API 运行根目录；
网关任务结束时在 job 根目录（`Output/jobs/<id>/`）写 `summary.txt` 指向运行目录。历史目录可用
`python3 tools/motion_summary.py --backfill` 补齐，或 `python3 tools/motion_summary.py <run_dir>` 只打印不写。
该工具只新增/覆盖这一个文本文件，不改 `result.json`、不回写哈希，也不改变运行的通过/失败判定。

CSV 表头可能带额外 `ribbon_guard_v1` 标记；它是文件保护标识，不是第八关节，数据行仍为时间加七关节数值。不要自行重写格式。

`--from-run` 的 `result.json` 关键字段：

- `resume_source`：源运行目录、level、源 status/outcome、检查点/任务/轨迹/guard/起点哈希、源仿真/预检记录、复用警告、`tool_changed`；
- `simulation_source`：复用仿真时，源 `simulation/summary.json`、`actual.csv`、`commanded.csv` 的路径与哈希；本次目录不复制这些大文件；
- `simulation_reuse_skipped`：源仿真不可复用、本次重跑的原因；
- `start_state_check`：当前/规划关节、逐关节差、TCP、判定、归位路径预测；选 `HOME` 时另有 `after_prompt`（操作员确认后重测）和 `after_correction`（归位后重测）；
- `start_correction`：`home_pose` 回执、审计路径、目标、时长、限制说明；
- `checkpoint`：本次 prepare 写出的检查点级别、路径、哈希（execute 运行没有）。

复用的仿真证据仍保存在源运行目录；`simulation_source` 给的是源路径和 SHA256，不是新副本。源目录被移动或修改后，复用会失败或改为重跑，不能把源证据当成新运行目录里的文件。

大模型结束时至少报告：运行目录、模式、`status/outcome`、是否完成真机任务、是否采集、失败阶段/错误码（如有）。对于 `offline_checks_passed` 只能说离线检查通过；对于 `failed/cancelled` 不宣称已到目标，即使已有部分轨迹或记录。`--from-run` 还要报告源运行 id、`resume_source.level`、是否复用仿真、`start_state_check.action`（`execute_direct` / `corrected_to_planned_start` / 失败）。

#### 15.7 失败与验证范围

**失败运行归档（2026-10-22）。** `pipeline_runs` 中 `status` 非 `succeeded` 的 65 个运行已移到
`pipeline/archive/failed_runs_20261022/`，原相对路径（含分组/实验子目录）保持不变，目录里有
`README.md` 分类统计与恢复命令、`index.tsv` 逐条索引；每个运行自带的 `motion_summary.txt` 随目录一起移动。
`Output/jobs/<id>/` 的失败任务没有移动（任务目录与 `Output/jobs.sqlite` 绑定），其运行目录仍在
`Output/jobs/<id>/outputs/<run>/`。归档只移动目录，不改 `result.json`、日志或轨迹；恢复时用 `mv` 移回同名相对路径。

**失败构成（2026-10-22 盘点，含分组子目录）。** 65 个失败中：规划阶段 49 个（40 个“直线段只走了一部分”，集中在
`ribbon_feasibility_20261018` 与 `e4_individual_limits_20261018` 两批扫描；7 个 X 下限；1 个无完整解；1 个规划器进程退出）、
真机执行中断 5 个（4 次 libfranka `communication_constraints_violation` reflex、1 次执行侧 X 下限）、
丝带调平 4 个、仿真 3 个、预检 2 个、适配器未配置 1 个、工作区被占用 1 个。`Output/jobs` 另有 7 个失败任务
（规划 3、真机 reflex 2、调平 1、`ROBOT_NOT_IDLE` 1）和 7 个取消任务。真正动过机械臂的失败只有 7 次，
其余都停在运动之前；分类明细见归档目录的 `ANALYSIS.md` 与 `index.tsv`。

默认准备适配器要求机器人 idle、各关节速度绝对值 ≤0.02 rad/s、实测关节与轨迹首点最大差 ≤0.01 rad，且 X 边界满足要求。起点不符会拒绝，**不自动移动到首点**，不自动错误恢复、不发送夹爪动作。适配器本身仍不移动；`--from-run` 的 `HOME` 归位发生在 `robot_prepare` 之前，需操作员确认，且受 15.9 的关节/TCP/朝向/X 包络限制。

Gazebo/预检目前沿用旧执行器模型，默认真机执行器使用 `quintic_hermite`。准备阶段会用当前执行器 dry-run 检查，但仿真并非同一命令流的完整验证。仿真需七关节最大误差均 ≤0.02 rad，记录覆盖主轨迹；相邻记录间隔超过 100 ms 时只允许“静止空洞”（空洞两侧实测关节逐关节相同），运动中仍然失败。这些指标不预测真实 ribbon 接触和受力。现场空间仍需核对。

| 现象 / 错误 | 下一步 |
|---|---|
| `validate` 失败、unknown fields、start_state_file 缺失 | 修正字段、单位或实际文件路径，重新进行静态校验；部分 Python 校验异常在外层显示 INTERNAL_ERROR，应读 message |
| `CALIBRATION_FAILED` / ribbon_level 暂停 | 检查 marker 可见性、端点识别、拉伸响应、累计状态；处理现场再决定恢复，不盲目加步长或重置累计量。若报方向低于下限，先确认 `marker_sets` 没选错；确认是同一条带子时请维护者下调 `axis_ratio_min`，不要据此判定 ribbon 没沿 x 放。plan/prepare 若只是连不上设备，应走默认起点降级，而不是反复 RESUME |
| `DEFAULT_START_POSE_MISSING` / `DEFAULT_START_POSE_INVALID` | 降级路径找不到或不能解析 `planner_start_pose_file`：检查 `--ribbon-params` 的文件路径、起点文件是否存在、是否带 `ribbon_mount: flange_58mm_v3` 和七关节 `joint_positions`。不能伪造起点继续规划 |
| `PLANNING_FAILED` / incomplete linear path | 看 planning.log 和失败预览；核对轴、姿态、关节余量和路径。不能未经用户同意将 linear 改成 free |
| `RIBBON_X_FLOOR_FAILED` / `RIBBON_GUARD_*` | 查实测边界、规划路径和 guard 配对；不能通过移动下界或去标记规避 |
| `SIMULATION_*` | 读取 simulation.log 与 summary（含 `video` 字段），查控制器、跟踪/覆盖；无界面已不是原因，直接看日志；不直接跳到真机。录像失败本身不会产生 `SIMULATION_*` |
| `PREFLIGHT_FAILED` | 根据具体 FAIL 修正轨迹；WARN 也需保留原报告 |
| `robot_prepare` 的 PROCESS_FAILED / `ROBOT_NOT_READY` | 查 host_readiness.log、robot_prepare.log 和状态回执；`--from-run` 的起点漂移先按 15.9 判定，超出包络才重测/重新规划 |
| `RESUME_SOURCE_*` / `RESUME_HASH_MISMATCH` / `RESUME_ARTIFACT_INVALID` | 源运行没有成功的 plan、没有可用检查点、缺少 `result.json`，或 task/trajectory/guard/起点/仿真哈希不一致。注意：prepare 在仿真/预检阶段失败但已写出对应 level 检查点的源仍可复用；用原始运行目录，不改写源文件；必要时重跑 prepare，不能手工补哈希或复制半个运行目录 |
| `RESUME_ROBOT_MISMATCH` | 源运行记录的 `robot_ip` 与本次 `--ribbon-params` 不同。不要跨机械臂复用轨迹；改回同一台机器人的参数或重跑 prepare |
| `ROBOT_STATE_UNAVAILABLE` / `ROBOT_STATE_INVALID` / `ROBOT_NOT_IDLE` | `--from-run` 起点校验读不到状态、q/dq 无效，或 `robot_mode≠1` / `max|dq|>0.02`。检查 FCI、Desk 模式、是否有其它程序占用；处理后再重跑，**没有任务运动发生** |
| `START_STATE_DRIFT` / `START_DRIFT_RELEVEL_REQUIRED` | 当前关节与轨迹首点差超过 0.20 rad，或归位路径包络不通过，或操作员选 `RELEVEL`。本次**没有任务轨迹运动**；`error.details.relevel_command` 给出重新调平+规划的命令，旧 trajectory 不能继续用 |
| `START_CORRECTION_FAILED` / `START_CORRECTION_INCOMPLETE` | `home_pose` 启动/连接/回执失败，或归位后重测仍 >0.008 rad。读 `start_correction`、`start_state_check.after_correction` 和 `start_correction.log`；不要假定机械臂已回到起点，先按现场状态处理，必要时重新调平 |
| `SIMULATION_REUSE_CHANGED` | 复用仿真前发现源 summary/actual/commanded 或轨迹哈希变化。回到源运行确认文件，或不用 `--from-run` 重跑 prepare；不能改源文件后继续 |
| `robot_execute` 失败 / `EXECUTION_UNCONFIRMED` | 保留日志与审计，按可能已经部分移动处理，先确认现场状态；不自动恢复并重发 |
| `communication_constraints_violation` / `control_command_success_rate` 明显偏低 | **常见 FCI 通信/实时性 reflex，不是轨迹、起点、权限、ribbon guard 或碰撞阈值错误。** 机器人可能已执行 startup transition 和一小段轨迹；先读新的 `read_franka_state` 确认 `robot_mode=1`、关节速度很小且无活动 job，再按原不可变规格重跑。不要改轨迹、重新规划或放宽碰撞阈值；若重复出现，再查网线/接头/交换机、机器人网段占用、IRQ/CPU 隔离和后台负载 |
| `PIPELINE_BUSY` / ROS 域冲突 | 查现有会话；不要杀掉不明进程或删除锁文件。锁文件存在本身不等于被占用 |
| `STAGE_TIMEOUT` | 查实际卡住阶段；超时不代表未运动，尤其在执行阶段 |

> **通信 reflex 的判读（2026-10-19 实测）**：日志出现
> `libfranka: Move command aborted: motion aborted by reflex! ["communication_constraints_violation"]`
> 与 `control_command_success_rate: 0.11` 时，应按 FCI 控制命令未按时到达处理，不要先怀疑轨迹。
> 正常成功运行的成功率通常约 0.95–0.99；明显低于 0.9 时先不要继续完整轨迹。该错误可能间歇出现，
> 同一规格重跑通常可恢复；但必须由用户确认现场空间、ribbon 余量和 reflex 已清除后发起，
> **不自动重试**，也不要在 reflex 未清除时发送新的运动命令。若多次重跑仍复现，再按通信链路和
> 主机实时性排查（网线/接头/交换机、`172.16.0.0/24` 网段占用、`eno1` IRQ 亲和性、CPU 隔离、后台负载）。

#### 15.8 ATI 六维力采集：现场前提与判读（2026-10-16）

- **启用范围**：只有 `execute` 模式、`execution_confirm` 通过之后才启动，与动捕同一时刻开始；
  调平阶段不使用力传感器。默认开启且与动捕同等严格：启动 20 秒内收不到样本、中途断流、
  未覆盖运动时段、文件缺失或为空都会以 `FORCE_*` 中止，不会在缺数据时继续真机运动。
- **网络前提**（2026-10-16 核对）：ATI Net F/T 设备地址是 `172.16.0.5`，主机接它的 USB 网卡是
  `172.16.0.10/24`，另有一条 `172.16.0.5/32` 主机路由把它钉在该网卡上。ATI 与 Franka 同在
  `172.16.0.0/24`，两块网卡会互相抢路由，所以不要动机械臂网卡 `eno1`（`172.16.0.1/24`）和
  动捕网卡（`10.1.1.198/24`）。用 `ip route get 172.16.0.5` 验证，结果必须显示 ATI 的 USB 网卡，
  不能是 `eno1`，更不能是 `lo`。链路 100 Mb/s 是接口盒上限，不是故障。
- **标定退化（重要）**：换算系数读自设备 `netftapi2.xml` 的活动标定。Net F/T 的嵌入式网页服务器
  并发能力极弱：同时用浏览器/curl 打开会让它收下 TCP 连接却不回包，此时标定读取超时，采集退化成
  **只记录原始 counts**（`units` 全为 `counts`、`calibrated=false`），UDP 数据通道不受影响。
  卡死时先清连接（`sudo ss -K dst 172.16.0.5`），仍不行再给接口盒断电重启；访问网页时只开一个标签页。
  **counts 不是 N/N·m，不得当力值或力学结论报告**；出现 `calibrated=false` 时按“本次没有可用力值”说明。
- **系统代理**：设备网页走 HTTP，会被 Clash 之类系统代理劫持（curl 报 502）。采集适配器读标定时已
  显式禁用代理，不受影响；人工访问时用 `curl --noproxy '*'`，并把 `172.16.0.5`、`172.16.0.3`、
  `10.1.1.198` 等 IP 字面量加进代理绕过列表（`172.16.0.0/12` 这类 CIDR 部分客户端不认）。
- **独立使用**（不启动机械臂，也不占用 pipeline）：

  ```bash
  python3 ~/ribbon_ws/ati/ati_capture_adapter.py --run-dir ~/ati_runs/probe --duration 10
  python3 ~/ribbon_ws/ati/ati_capture_adapter.py --run-dir ~/ati_runs/probe --demo   # 无硬件预览
  python3 ~/ribbon_ws/ati/ati_force_plot.py --run-dir ~/ati_runs/probe
  ```

  协议、CSV 列、状态/回执字段、`FORCE_*` 错误码与图像细节见 docs 内的 [PIPELINE.md](PIPELINE.md)
  的 §ati_capture 与 §力数据图。读数不做滤波、不去零、不写设备配置，只用于记录与事后分析。
- **首次上机实测（2026-10-16 01:03，run `20261016_010323_4d1a2efa`）**：`execute` 全链路成功
  （`status=succeeded`、`outcome=executed_and_captured`），力采集 1777 个样本、实测 49.7 Hz、
  覆盖 35.7 s 的运动时段，`force/force.png` 与 `force/force_plot.json` 正常生成；但那次 Net F/T
  标定读取超时，`calibrated=false`、单位是 counts，只能用来看时序/波形，不能当力值。
  **结论：力采集已经过真机执行验证；要拿到 N/N·m 读数，必须先解决标定读取（网页并发/代理）再上机。**

#### 15.9 复用 plan/prepare：检查点与起点校验（2026-10-18）

**用途：** 把耗时的调平/规划/仿真和最终 execute 拆开。`plan`/`prepare` 每个离线阶段成功后写
`checkpoint.json`；之后用 `--from-run` 在新目录复用已冻结的输入，跳过调平/规划/仿真（按源 level），
但**不跳过**预检、`robot_prepare`、最终 `MOVE` 和采集。execute 前按关节空间比较当前起点与
`trajectory.csv` 首点，必要时通过远程确认 `HOME` 归位，或 `RELEVEL`/`QUIT` 退出。

**为什么必须比较关节，不只比较 TCP：** 7 自由度冗余臂可以以不同关节角回到同一 TCP 位姿；
调平或上一次执行后 TCP 只差几毫米、关节却可能差几十度（本机 2026-10-18 实测 B/G 同 TCP 差 68.7°）。
`execute_offline` 只检查关节首点（0.01 rad），所以 pipeline 在它之前增加同一口径的关节检查。

##### 15.9.1 检查点

非 execute 模式在每个离线阶段成功后写本次目录的 `checkpoint.json`：

| 阶段 | level | 复用时可跳过 | 说明 |
|---|---|---|---|
| plan 成功 | `plan` | 调平、规划 | 只有轨迹/guard/起点；没有仿真/预检 |
| simulate 成功 | `simulate` | 调平、规划、仿真 | 有仿真摘要/actual/commanded |
| preflight 成功 | `prepare` | 调平、规划、仿真 | 预检仍在本次 execute 重跑 |

检查点按 level 记录 `task.yaml`、`trajectory.csv`、`trajectory.csv.yaml`、
`trajectory.csv.ribbon_guard`、冻结起点关节，以及已到达阶段的仿真摘要、`preflight.json`
的路径与 SHA256，还有 `run_pipeline.py` / `pipeline_resume.py` 的哈希。写入失败只记 `result.json` 的 `checkpoint_warning`，不会把已经成功的
plan/prepare 判失败。execute 运行不写检查点；它自己的轨迹和回执仍保存在该次运行目录中。

**源运行目录保持不变。** `--from-run` 总是新建 `pipeline_runs/<时间戳>_<标识>/`，复制不可变输入，
不会改写或续写源运行。检查点不是“可编辑的状态文件”；手工改源文件会导致哈希不一致并按 15.7 拒绝。

##### 15.9.2 用法与源 level

先 prepare，稍后只补执行：

```bash
# 1) 调平 → 规划 → 仿真 → 预检，写 checkpoint.json
python3 tools/run_pipeline.py \
  --task /home/zhaoyunzyq/ribbon_ws/trajectories/my_ribbon_task.yaml \
  --mode prepare

# 2) 稍后复用，只做起点校验 + robot_prepare + MOVE + 执行 + 采集
python3 tools/run_pipeline.py \
  --from-run /home/zhaoyunzyq/ribbon_ws/pipeline/pipeline_runs/<prepare_run_id> \
  --mode execute
```

只想先 plan、稍后再补仿真/预检：

```bash
python3 tools/run_pipeline.py --task /abs/path/task.yaml --mode plan
python3 tools/run_pipeline.py --from-run pipeline_runs/<plan_run_id> --mode prepare
```

`--from-run` 接受运行目录、该目录的 `result.json` 或 `checkpoint.json`。它不能配 `--task`
（任务来自源运行）、`--scene`、`--skip-leveling` 或 `--mode plan`。

| 源 level | `--from-run --mode execute` 做什么 |
|---|---|
| `plan` | 本次补仿真、预检，再 `start_check`、`robot_prepare`、`MOVE`、执行、采集 |
| `simulate` | 复用仿真（重新校验摘要/actual/commanded 哈希与覆盖），重跑预检，再同上 |
| `prepare` | 复用仿真，重跑预检，再同上 |
| 源是 execute / 没有成功 plan / 哈希不一致 | 拒绝，不运动 |

以下内容**不会**复用或跳过：

- **预检**每次在本次目录重新运行，用当前执行器模型/URDF 复核；
- **`robot_prepare`** 每次执行都重新跑：读当前状态、`execute_offline` dry-run、重算 ribbon X 边界；
- **最终 `MOVE` 确认**、两路采集、执行回执校验与原流程完全一致；
- 源运行如果来自 `default_start_pose_fallback`，仍只有当前机械臂真在那个冻结起点时才继续，
  该起点本身不能证明现场状态。

旧运行没有 `checkpoint.json` 时，只有 `result.json` 为 `succeeded` 的 plan/prepare 才会从阶段列表
和产物推导检查点；仍然复核所有哈希，警告写入本次 `resume_source.warnings`，推导不写回源运行。

##### 15.9.3 execute 前的起点校验

读取当前关节（要求 `robot_mode=1`、`max|dq|<=0.02`），与 `trajectory.csv` 第一行逐关节比较：

| `max|Δq|` | 行为 |
|---|---|
| `<= 0.008 rad` | 直接执行；`execute_offline` 还会再复核 0.01 rad |
| `0.008–0.20 rad` | 用 guard 的冻结 FK 预演 `home_pose` 归位路径；满足包络才询问 HOME/RELEVEL/QUIT |
| `> 0.20 rad` 或路径不安全 | `START_STATE_DRIFT`，**本次没有任务轨迹运动**，要求重新调平+规划 |

归位路径判据（201 点，关节空间五次插值，与 `home_pose` 同一几何路径）：

- TCP 相对起点-终点直线的最大偏离 `<= 1.0 mm`；
- TCP 朝向相对起点的最大偏离 `<= 2.0°`；
- TCP X 不低于 guard 的 `minimum - 0.65 mm`（与执行器 ribbon X 容差一致）。

通过后显示预测值，等待输入（可由 `robot_pipeline_confirm` 远程发送，或 attach 输入）：

```text
HOME      用 home_pose 归位到本次轨迹首点；归位后重测，必须 <=0.008 rad
RELEVEL   放弃复用；退出并打印重新调平+规划的命令
QUIT      退出
```

选择 `HOME` 后，流程会再读一次当前关节并重跑同一套包络检查（等待确认期间机械臂被移动时会重新
判定），通过后才调用 `home_pose`；归位后再读一次，仍 >0.008 rad 则以 `START_CORRECTION_INCOMPLETE`
退出。`--on-start-drift abort` 不询问，超过直执行阈值直接退出；非交互终端也不会询问。

`home_pose` 的目标文件是本次目录里由轨迹首点生成的 `planned_start_pose.yaml`，不是共享的
`planner_start_pose_file`（后者可能已被后来的调平改写）。`HOME` 是**真实运动**；`home_pose`
不做 MoveIt 碰撞检查，也没有自带的 ribbon X guard。本流程的包络是离线运动学预测，只约束
TCP/朝向/X，不估计 ribbon 张力、接触或绳索/夹具碰撞；启动前仍须确认工作空间和余量（可由用户远程核对状态与录像，不由本工具自动判定安全）。

**为什么 `RELEVEL` 不能继续用旧轨迹：** 重新调平会改变起点关节，而 `trajectory.csv` 第一行绑定
的是旧起点；7 自由度冗余臂即使 TCP 相同也可能在不同关节解上。`RELEVEL` 的语义是“退出，重跑完整
execute”，错误里会打印 `--task ... --mode execute`（连同本次的 `--ribbon-params` / `--config` /
`--scene`）；不会在本进程里接着执行旧轨迹。

##### 15.9.4 执行结束后回起点？

**任务可声明 `return_to_start_joints: true`（2026-10-19 起）。** 设置后，规划器在最后一段之后
追加一段保持 TCP 位姿的零空间自运动，把七个关节送回本任务声明的起点关节角；执行成功即回到首点，
不再需要手工 `home_pose`。修正段逐点检查关节限位、冻结 X 下界和 `/check_state_validity` 碰撞；
任一项不通过就**只 WARN 并跳过**，本次 plan/execute 不受影响，`trajectory.csv.yaml` 的
`joint_return.status` 会写 `applied` 或 `skipped` 及原因。

没有设置该字段、或 `joint_return.status: skipped` 时，execute 成功后仍不会自动回到起点：
轨迹末段只保证回到起始 TCP/位姿，不保证关节回到首点；7 自由度冗余臂可能停在同一 TCP 的不同
关节解上。

需要立即回起点时，手动运行 `home_pose`（启动即运动，不等待 Enter，见第 12 章）：

```bash
# 正常 execute 运行
ros2 run franka_robot_driver home_pose \
  --start-pose /home/zhaoyunzyq/ribbon_ws/pipeline/pipeline_runs/<run_id>/franka_start_pose.yaml \
  --time-scale 5.0 \
  --ros-args -p automatic_error_recovery:=false

# --from-run execute 运行
ros2 run franka_robot_driver home_pose \
  --start-pose /home/zhaoyunzyq/ribbon_ws/pipeline/pipeline_runs/<run_id>/planned_start_pose.yaml \
  --time-scale 5.0 \
  --ros-args -p automatic_error_recovery:=false
```

也可以用下一次 `--from-run execute` 的起点校验：如果手臂还在上一条轨迹终点附近，它会在
`robot_prepare` 前比较当前关节与轨迹首点，并在包络内提示 `HOME`。先检查漂移：

```bash
python3 /home/zhaoyunzyq/dsh/franka/check_start_drift.py \
  /home/zhaoyunzyq/ribbon_ws/pipeline/pipeline_runs/<run_id>/trajectory.csv
```

`home_pose` 是关节空间五次插值，不做 MoveIt 碰撞检查，也不带 ribbon X guard；夹着 ribbon 时
即使目标是以前的调平姿态，途中也可能拉扯或越过边界（实测漂移 10–23° 时 TCP 偏离 0.2–1.8 mm）。
漂移较大（例如 B/G 这种大分支差）时，不要用 `home_pose` 硬拧，按 `START_STATE_DRIFT` /
`RELEVEL` 重新调平+规划。`return_to_start_joints` 的修正段不是直线插值，而是保持 TCP 位姿的
零空间自运动，X 下探约 0，且受冻结 X 下界检查；这是与 `home_pose` 的关键区别。仍没有
`--post-home` 之类“执行后自动调用 home_pose”的接口；需要自动归位时用任务字段，需要手工兜底时
用 `home_pose`。

##### 15.9.5 参数与回执

新增参数（完整默认值见 15.5）：`--from-run`、`--on-start-drift {ask,abort}`、
`--start-ready-tolerance`（0.008 rad）、`--start-correction-limit`（0.20 rad）、
`--correction-path-tolerance-mm`（1.0）、`--correction-orientation-tolerance-deg`（2.0）、
`--correction-time-scale`（5.0）、`--correction-min-duration`（5.0 s）、`--correction-timeout`（600 s）。

`--from-run` 的 `result.json` 关键字段：

- `resume_source`：源运行目录、level、源 status/outcome、检查点/任务/轨迹/guard/起点哈希、
  源仿真/预检记录、复用警告、`tool_changed`；
- `simulation_source`：复用仿真时源 `summary.json` / `actual.csv` / `commanded.csv` 的路径与
  SHA256；大文件仍在源运行目录，不复制到本次目录；
- `simulation_reuse_skipped`：源仿真不可复用、本次重跑的原因；
- `start_state_check`：当前/规划关节、逐关节差、TCP、判定与归位路径预测；选 `HOME` 时另有
  `after_prompt`（确认后重测）和 `after_correction`（归位后重测）；
- `start_correction`：`home_pose` 回执、审计路径、目标、时长与限制；
- `checkpoint`：prepare 写出的检查点级别、路径、哈希（execute 没有）。

失败错误码与处置见 15.7 的 `RESUME_*` / `START_*` 行。

##### 15.9.6 已知限制与离线验证

- 本功能不替代 `execute_offline` 自己的 0.01 rad 起点检查、ribbon X 边界检查、libfranka 实时检查；
  它只在前面增加一层**关节空间**起点判定，并在允许时提供一次可审计的归位。
- 归位包络是**离线运动学预测**，不是碰撞检查、不是实时力/张力约束；`home_pose` 的路径跟随容差
  和实际跟踪误差仍可能让真实 TCP 偏离预测值，现场必须留余量并确认 ribbon 状态。
- 大分支差（如本机 B/G 同 TCP 差 68.7°）会先被 0.20 rad 关节上限拒绝；即使单独评估归位路径，
  guard FK 也给出 TCP 路径偏离 **17.30 mm**、朝向 **5.58°**、X 余量 **-7.58 mm**，因此不会
  尝试归位。单关节 2° 偏移在 0.044 mm / 2.00° / X 余量 0.65 mm 边界内通过，2.5° 即被拒绝；
  默认 2° 偏保守。
- guard FK 在历史起点上与 guard 的 `minimum` 差约 `1.6e-10 m`；这些是离线核对，不是真机运动验证。
  新增 17 项无硬件测试，覆盖 checkpoint 复制/哈希、plan→prepare→execute 链、直接执行、
  HOME 归位和过大漂移阻断；连同相关既有测试共 29 项通过。本功能开发时未执行真机运动；
  第一次现场使用请用短、低风险轨迹验证 direct / HOME / RELEVEL 三条路径。
- 大漂移的自动归位需要位姿约束零空间自运动（OMPL constrained 或 Jacobian 零空间积分），
  当前实现没有做；在此之前，大漂移一律重新调平+规划。

#### 15.10 USB 摄像头录像：默认 1080p30 与判读（2026-10-18）

- **启用范围**：只有 `execute` 模式、`execution_confirm` 通过之后才启动，与 Nokov/ATI
  同一时刻；调平阶段不使用摄像头。默认开启且与动捕/力采集同等严格：打不开、中途断流、
  没有覆盖运动时段、文件缺失或为空都会以 `CAMERA_*` 中止，不会在缺视频时继续真机运动。
  置 `usb_capture: null` 即关闭；成功结果仍是 `executed_and_captured`，只是没有视频。
- **实现**：`~/ribbon_ws/camera/usb_capture_adapter.py`，复用 `camera/usb_cam.py` 的
  V4L2 设备枚举，不新增 ROS 包、不依赖机械臂 SDK。默认自动选择非内置 USB 摄像头；
  本机 sysfs 识别到内置 `/dev/video0` 与 `1080P USB Camera`（通常为 `/dev/video2`），
  以现场 `python3 ~/ribbon_ws/camera/usb_capture_adapter.py --list` 为准。
- **模式**：请求 1920x1080 @ 30 fps，输入 MJPEG（UVC 在 USB2.0 下只有 MJPEG 能跑满
  1080p30），输出 H.264（`avc1/.mp4`）。打开后核对实际宽高；设备不给 1920x1080 时
  默认直接失败，不静默录成低分辨率；确实要降级时加 `--allow-size-fallback`，回执会记
  `size_fallback=true` 和实际尺寸。帧率同时记录设备回报值和实测值；实测平均低于目标
  80% 只写 warning，不改变采集判据；实际跑在 60fps 时按名义 30fps 丢帧并记
  `dropped_frames`。
- **产物**（本次 `pipeline_runs/<run_id>/` 下）：
  - `usb_camera_<run_id>.mp4`：视频；编码不可用时自动回退 `mp4v/XVID/MJPG`，实际编码见回执。
  - `usb_camera_<run_id>_frames.csv`：逐帧
    `frame_index,wall_unix_ns,wall_iso,elapsed_s,width,height`。`frame_index` 从 0 开始，
    与视频帧号一一对应；`wall_unix_ns` 与 Nokov/ATI 同源，可按时间戳离线对齐。
  - `usb_camera_<run_id>_meta.json`：设备、实际分辨率、帧率、编码、帧数、warning。
  - `camera_status.json`：运动期间心跳（原子写）；`camera_result.json`：最终回执，
    字段含 `completed / sample_count / first_frame_unix / last_frame_unix / files /
    width / height / nominal_fps / measured_fps / codec / video_readable / warnings`。
  - `result.json` 里的键是 `camera_capture`；`artifacts` 会列出所有文件的绝对路径。
- **运行时序**：适配器写出第一帧、状态变为 `ready` 后才开始 `robot_execute`；运动结束后
  流水线等到运动结束之后的一帧，再写 `camera_stop.json`。因此视频包含运动前很短的预录
  和运动后的一帧收尾，不是从第一个运动指令才开始采集。
- **CPU**：H.264 编码在 1080p30 下约占用 1 个 CPU 线程；适配器把 OpenCV 线程数限制为 2，
  且真机执行前流水线会关闭 Gazebo 释放主机资源。若现场主机仍跟不上，优先把
  `--codec` 改为 `mp4v` 或降低分辨率（需同步改 `pipeline_adapters.yaml`），不要直接
  放宽 1 kHz 控制回路的实时要求。
- **验证范围**：`camera/tests` 与 `pipeline/tools/tests/test_pipeline_camera_integration.py`
  已通过无硬件测试（`--demo` 合成画面、假执行器/假动捕/假力采集），覆盖 1080p30 落盘、
  停止文件/SIGTERM 收尾、原子状态、三路同时启动、失败阻止真机等路径。2026-10-19 又在
  本机真实 USB 摄像头上单独验证：自动选择 `/dev/video2`、MJPG 输入、H.264 输出、
  1920x1080 @ 30 fps，实测平均约 29.8 fps，停止文件协议收尾正常。**尚未与真机机械臂
  同场跑过整条 execute 链路**；首次上机前仍建议按 15.10 的 `--list` 和单独录像命令
  再确认一次设备、分辨率与帧率，再走完整 pipeline。
- **单独使用**：

  ```bash
  python3 ~/ribbon_ws/camera/usb_capture_adapter.py --list
  python3 ~/ribbon_ws/camera/usb_capture_adapter.py --run-dir ~/camera_runs/probe --duration 10
  python3 ~/ribbon_ws/camera/usb_capture_adapter.py --run-dir ~/camera_runs/demo --demo --duration 2
  ```

  协议、产物列、状态/回执字段与 `CAMERA_*` 错误码详见 docs 内的 [PIPELINE.md](PIPELINE.md)
  的 §usb_capture。录像只用于记录与事后分析，不参与任何实时闭环控制。

### 16. 任务 YAML：run_pipeline 的输入格式

**撰写要求：** 本章规定输入格式；完成文件还必须满足 15.2.1 的逐份 prepare 验证门槛。
示例可解析、表格数值吻合或只完成静态校验，均不能代替可达性和完整路径验证。

**已有 YAML 的执行入口（不要绕过）：** 终端里用第 15 章的 `python3 tools/run_pipeline.py --task <绝对路径> ...`；tool-chat/tool-agent 里用 18.2 的 `robot_pipeline_list_tasks` / `prepare_robot_pipeline_remote_task` 按路径准备任务，再用 `robot_pipeline_submit` 登记、`robot_pipeline_start` 启动。终端 `--task` 与远端 YAML 工具跑的是同一个 pipeline、同一套校验；`prepare_robot_pipeline_spec` 只用于还没有 YAML、需要从结构化参数生成规格的场合。`--from-run` 复用运行时不接受 `--task`：任务来自源运行，见 15.9。

位置、朝向的物理含义及坐标关系见第 4 章。本节保留字段类型、单位和参考语义，便于正确填写 API 输入。

#### 16.1 推荐任务骨架

填值前参照第 4.4–4.6 节：长轴从夹持端→固定端为 base +X，正宽度/厚度定义为 +Y/+Z。保存起点中 tool +Z/+X/+Y 分别近似对应这三轴；严格绕 base 长轴使用 base x，不把近似 tool z 当作完全等价。名义夹持点取 TCP，真实重合未经测量；当前省略 ribbon_workspace。

以下完整示例另存于 `docs/examples/ribbon_boundary_example.yaml`。数值仅用于说明语法，未作本次硬件验证；`+3 mm` 不是经验证的受力安全裕量。

```yaml
ribbon_task: true
frame_id: base
end_effector_link: fer_ribbon_tcp
position_reference: start
start_state_file: /home/zhaoyunzyq/ribbon_ws/ros/src/franka_motion_planner/config/franka_start_pose.yaml
start_state_source: declared
require_start_state: true
x_floor:
  link: fer_ribbon_tcp
  minimum: start
velocity_scaling: 0.05
acceleration_scaling: 0.05
planning_time: 20.0
keep_orientation: true
orientation_tolerance: 0.01
waypoints:
  # 所有 position 均相对同一个调平后起点。
  - position: [0.003, 0.0, 0.0]
    motion: linear
  # 同 TCP 位置，绕 base +X（参考装夹长轴）转 +15°。
  - position: [0.003, 0.0, 0.0]
    motion: linear
    keep_orientation: false
    rotation: {axis: x, angle_deg: 15.0, frame: base}
    hold_seconds: 1.0
  # 保持转后朝向，base +X 再走 5 mm：目标偏移为 8 mm。
  - position: [0.008, 0.0, 0.0]
    motion: linear
  # 在当前目标位置反向旋转。
  - position: [0.008, 0.0, 0.0]
    motion: linear
    keep_orientation: false
    rotation: {axis: x, angle_deg: -15.0, frame: base}
  # 回到 +3 mm 的目标，不是调平起点本身。
  - position: [0.003, 0.0, 0.0]
    motion: linear
    hold_seconds: 1.0
```

输入文件在调平前也会校验，所以 `start_state_file` 必须已经存在且格式有效。它仅供第一次校验；pipeline 随后会替换成本次调平快照。不要编造七关节角以绕过缺失起点。使用绝对路径：相对文件路径按任务 YAML 所在目录解析，而 pipeline 会先复制任务到运行目录，可能导致引用失效。`package://` 可解析，但可能指向安装目录旧副本，推荐上述源码文件绝对路径。

#### 16.1.1 从本任务规划结果读取 tool→base 关系

读取本任务生成的 `trajectory.csv.yaml`，以第一段的 `start_orientation_xyzw` 得到规划初始 TCP 朝向；后续段选择对应 segments 项。下面只读生成文件，不连接机器人，不读取 docs 外既有配置：

```bash
python3 - /absolute/path/THIS_RUN/trajectory.csv.yaml <<'PY'
import sys, math, yaml
with open(sys.argv[1]) as f:
    d = yaml.safe_load(f)
if d.get('frame_id') != 'base' or d.get('end_effector_link') != 'fer_ribbon_tcp':
    raise SystemExit('Unexpected frame/link')
x, y, z, w = d['segments'][0]['start_orientation_xyzw']
n = math.sqrt(x*x+y*y+z*z+w*w)
if not math.isfinite(n) or n < 1e-9:
    raise SystemExit('Invalid quaternion')
x,y,z,w = (v/n for v in (x,y,z,w))
R = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
print('R_base_tool rows:', R)
for i, axis in enumerate('XYZ'):
    print('tool +' + axis + ' in base:', [R[j][i] for j in range(3)])
for i, material in enumerate(('length +baseX', 'width +baseY', 'thickness +baseZ')):
    print(material + ' in tool:', R[i])
PY
```

这里是规划模型姿态，不是执行后实时状态；不能用旧结果代替当前朝向。相对旋转的 frame/axis 含义应在规划前确定；首次没有当前规划结果时，严格按用户 base 轴目标表达可避免依赖近似 tool 轴对应。

#### 16.2 顶层字段

未知字段直接报错；布尔值使用 YAML `true/false`，不要使用字符串。所有数值须有限，不能使用 NaN/Infinity。

| 字段 | 当前契约 |
|---|---|
| `ribbon_task` | 本流程强制 true；明确 false 被拒绝 |
| `frame_id` | ribbon 任务只能为 `base` |
| `end_effector_link` | ribbon 任务只能为 `fer_ribbon_tcp` |
| `position_reference` | ribbon 任务只能为 `start` |
| `start_state_file` | 起点 YAML；必须含七个弧度制 `joint_positions`，可包在 `start_state` 下；本流程的 ribbon 任务还要求 `ribbon_mount: flange_58mm_v3`，缺失会在调平后的校验被拒。`--from-run` 生成的任务副本指向内部 `planned_start_pose.yaml`，该副本是复用记录，不是供重新编辑的新任务输入 |
| `start_state` | 可替代文件的内联起点，二者互斥；常规任务推荐只引用文件 |
| `start_state_source` | 推荐 `declared`；ribbon 禁止 `live` |
| `require_start_state` | 推荐 true，调平后 pipeline 强制 true |
| `x_floor` | 只能为 `{link: fer_ribbon_tcp, minimum: start}`；省略时自动补入 |
| `velocity_scaling` | `[0.001, 1.0]`，默认 0.1，关节速度缩放系数，不是 m/s |
| `acceleration_scaling` | `[0.001, 1.0]`，默认 0.1，关节加速度缩放系数 |
| `planning_time` | `[0.1, 120]` s，默认 10，规划器规划时间参数，不是总流程超时 |
| `keep_orientation` | 默认 false；建议骨架设 true，再对旋转段显式覆盖 |
| `orientation_tolerance` | `[0.0001, 0.5]` rad，默认 0.01，每轴朝向误差容差 |
| `return_to_start_joints` | 可选 bool，默认 false。true 时在最后一段之后追加一段保持 TCP 位姿的零空间自运动，把七个关节送回本任务声明的 `start_state.joint_positions`；要求起点含 `joint_positions`，`live` 起点不支持。只有最后一段已回到起点位姿（如 `position: [0,0,0]` 且朝向恢复 R0）时才可能生效，否则位姿偏差按 pose drift 跳过。修正段逐点检查关节限位、冻结 X 下界和碰撞；不可行时只 WARN 并跳过，本次 plan 仍成功。见 15.9.4、16.4 |
| `waypoints` | 1–100 个目标，最后一个是终点；每项 position 必填 |
| `ribbon_workspace` | 可选球形距离检查，见 16.5 |

#### 16.3 每段目标字段

每个 waypoint 描述“从上一点到该点”的段；第一段从本次调平起点出发。

| 字段 | 当前契约 |
|---|---|
| `position` | 三个数 `[dx,dy,dz]`，单位 m；X 偏移不得为负 |
| `motion` | `linear` 或 `free`；默认 free。linear 要求完整直线路径，失败不自动绕路；free 允许规划器绕行 |
| `keep_orientation` | 继承顶层；true 时禁止同时填写下面任一朝向字段 |
| `orientation_tolerance` | 可覆盖顶层，同样以 rad 表示 |
| `hold_seconds` | `[0, 3600]` s，默认 0，到达后停留；终点也可使用 |
| `rotation` | `{axis: x/y/z, angle_deg: [-180,180], frame: base/tool}`，三项必填 |
| `orientation_xyzw` | 四元数顺序 `[x,y,z,w]`；模长与 1 相差不超过 0.01，加载时归一化 |
| `orientation_rpy_deg` | `[roll,pitch,yaw]`，度；固定 XYZ，`R=Rz(yaw)Ry(pitch)Rx(roll)` |
| `orientation_axes` | `{z_axis: [x,y,z], x_axis: [x,y,z]}`；两向量均非零，归一化后点积绝对值 ≤0.0001 |

四个朝向字段最多填写一个。位置相同、朝向不同可表达原地转动，但不保证该姿态有可行连续关节路径。大于 180° 的相对转动须拆段并明确顺序。

每个途经点均按停车方式定时，`hold_seconds: 0` 也不代表连续不停顿通过。当前不支持通过 YAML 指定精确到达时刻、恒定 TCP 速度或平滑连续过点；到达时间由规划结果给出。

#### 16.4 强制 X 下界

冻结边界为调平后 `fer_ribbon_tcp` 的 base X 坐标，后续段不会重新定义它。规划器对路径进行检查，导出 `trajectory.csv.ribbon_guard`；真机默认执行器再次验证 guard、命令路径以及实测状态。

当前执行保护允许相对冻结下界 **0.65 mm 负偏差**，这是实现容差，不是可规划的负 X 位移许可。目标仍须满足 `dx ≥ 0`。单纯目标 X 合格不能保证途中合格，尤其旋转和关节插值可能触发失败。不要自动修改保护阈值。

`return_to_start_joints` 追加的关节自运动同样按这个冻结下界逐点检查：它保持 TCP 位姿不变，
因此 X 下探通常 <0.1 mm；若某条自运动路径会越过下界，规划器只跳过该修正并 WARN，不改阈值。

该边界不是张力控制、完整碰撞检查或物理上永不越界的证明；模型、跟踪误差和停止延迟仍存在。

#### 16.5 可选 ribbon 距离约束与场景

**当前决定不启用 ribbon_workspace，任务中省略整个字段。** 名义夹持点取 TCP 不等于获得了固定端实测坐标，也不能确定有效 margin；现有强制 X guard 继续生效。只有后续明确要求此检查时才补齐实测参数，不能将上下文中的理论 anchor 估计当成实测。下面 null 是将来启用时的待测字段，**不是当前应填写或运行的配置**：

```yaml
ribbon_workspace:
  anchor: null                # 必填实测 [ax, ay, az]，base，m
  grip_offset: null           # 必填实测 [rx, ry, rz]，fer_ribbon_tcp 局部系，m
  length: 1.0                  # 有效长度，m
  margin: null                # 必填经现场确定的裕量，m；0 <= margin < 1.0
```

条件为 `length > margin ≥ 0`。规划后采样检查夹持点到 anchor 的距离 ≤ `length - margin`；不模拟 ribbon 形状、扭转、应力或与物体接触，也不自动重规划。

通过 `--scene <绝对路径>` 提供 MoveIt 障碍物。场景 YAML 只支持 `frame_id` 和 `boxes`，每个 box 的字段为唯一 `id`、正数 `size: [sx,sy,sz]`、`position: [x,y,z]`、可选 `orientation_xyzw`（默认单位四元数），均为 base 中绝对量，长度单位 m。场景不会自动同步进 Gazebo；默认真机执行器的 dry-run 不复查 MoveIt 碰撞场景。

### 17. 文档维护与权限内排障

目标模型的依据是本手册、docs 内其他说明，以及本任务的命令输出与生成文件。文档中的二进制、模块和配置路径用于调用，不是额外的源码阅读入口。

若命令行为与本文不符，保留本次 stdout/stderr、退出码和回执，说明差异并让维护者核对；不要读 docs 外源码、安装文件、旧日志或机器人配置来排障。终端 --help 可用于核对已文档化入口；避免尝试未经说明的命令，因为有的程序默认就会连接/运动。

文档中的 YAML 已通过解析校验，形状提取和绘图示例已由维护者用历史数据副本验证。这是既有验证记录，不授予目标模型读取历史文件的权限。本文档修订本身不连接设备、不执行运动。

---

## 第三部分 · 托管工具与视频

### 18. 2026-10-14 托管工具与视频补充

pro6000 的 ribbon-research hardware extension 已将本文档入口封装为固定参数 tools。read_franka_manual 仅能读取本目录的手册（即本文件），返回内容与 SHA256；不能指定任意路径。机器人状态、Nokov 查询/有限时长监视/记录、ribbon 分析/测量/会话状态、调平、归位、笛卡尔微动、已有轨迹校验/执行分别独立调用，不强制执行整个 pipeline。所有操作使用同一任务状态、日志、回执与成果清单。

归位/微动/已有 CSV 真机执行的托管包装会增加 MOVE 确认；不要把它误认为原生二进制本来就有此确认。该确认可由 `robot_pipeline_confirm` 远程发送当前提示的精确 choice，或 attach 输入；调平保留原生交互。dry_run 默认为 true；非运动不等于不占用 FCI 或不更新测量会话，执行时仍有独占锁。Nokov monitor 被宿主限定时长并以 SIGINT 正常结束。分析与归位/执行的输入仅来自明确指定的托管任务，进行路径和哈希校验，不能读取任意旧文件。

当前 bridge 在标定前纯格式校验允许缺少 start_state；标定后实际规划仍使用冻结实测起点。此行为补充旧版示例，不能将未测起点编造为关节状态。

新任务 prepare_robot_pipeline_spec 默认请求 simulation/ribbon 后处理，可用 videos 布尔字段明确关闭。run_pipeline.py 的 --video 和 --ribbon-video 均默认开启，--no-video / --no-ribbon-video 显式关闭；2026-10-20 起 --ribbon-video 默认只生成 videos/ribbon_viewer.html，两个 MP4 需额外的 --ribbon-videos。视频生成失败写警告，不修改真机执行回执。托管输出仍位于 ~/ribbon_ws/Output/jobs/<id>/outputs/<run>/，不自动复制到 pipeline_runs。robot_pipeline_render_videos 在已解决的终态任务中复用既有 Gazebo 相机视频；若无，则仅在隔离 Gazebo 中回放保存 trajectory.csv 补录；它显式带 --ribbon-videos，因此补录会生成两个 MP4。ribbon 重建从保存 marker 数据拟合，不重新启动标定、FCI、采集或真机执行。

机械臂视频仅采用原生 sim_replay.py --video 的 fer_review.sdf 相机画面，包含机器人模型；不生成或用骨架替代视频。分辨率 640×360，相机传感器配置 10Hz；MP4 编码帧率以回执为准，已核验示例及补录文件的编码元数据均约 25fps。新 pipeline 输出 simulation/gazebo_review.mp4；终态补录输出 videos/gazebo_replay_<id>/gazebo_review.mp4，其 summary 单独保存，不覆盖原始 result.json 或仿真验证报告。录像不可用时如实报告，不能用示例冒充任务录像。

现场已确认两边 marker 各自有材料长度顺序，但两边交错粘贴，同编号并非横向材料配对。ribbon 重建（默认 HTML；MP4 为可选项）分别拟合两条有序边，先把球心曲线按 rod_offset 内移再用卡尺实测带宽约束纵向错位及曲面；仅显示有观测的共同区段，不补足未观测的一米全长。缺失/退化帧保留缺失提示，不跨缺失段伪造数据。videos/ribbon_fit_diagnostics.json 保存纵向错位、观测跨度、球心垂距与宽度拟合误差；矩形宽度是模型约束，不是测得的材料坐标或力学解。Nokov world 与 robot base 尚无外参，重建结果不能用于证明机器人空间配准。

2026-10-14 历史样本附注与处置：既有采集（20261013，marker 为 **6mm 球**）的两排球心垂距中位数 57.42mm，与名义 24mm 宽度不一致，宽度拟合 RMS 中位数约 33.5mm。根因是 marker 由 1mm 双面胶 + 13mm 直杆 + 球半径横向抬出 ribbon 真实边缘，而拟合把球心当成了带面点。横向外偏 = 胶 1 + 杆 13 + 球半径：6mm 球 = 17.0mm，8mm 球 = 18.0mm；该批 6mm 球数据实测反推 16.71mm，与名义差 0.29mm（装配公差），也反证带宽≈24.0mm。现已在 pipeline_videos.fit_ribbon 修正：两条球心曲线先按“中位垂距最小”对齐（材料站位对应，与宽度/杆外偏无关），再各自内移 rod_offset，残差才对“实测垂距 vs 带宽+2×杆外偏”有判别力。旧 6mm 球数据：rod_offset=16.7mm 时 RMS 中位数 ≈1.0mm，用 8mm 球的 18.0mm 则 ≈2.9mm；而对齐错位在两种取值下都应稳定在 ≈91.4mm（修好前该值会随 rod_offset 漂到 86～110mm，把残差吸收掉，指标失去判别力）。默认 rod_offset_m 由 TAPE_THICKNESS_M+ROD_LENGTH_M+MARKER_DIAMETER_M/2 推出，当前 8mm 球 = 0.018；换球径必须同步改 MARKER_DIAMETER_M。可用 pipeline_videos.py --rod-offset-m（数值或 auto）与 --nominal-width-m 覆盖；auto 用本次数据的中位垂距去均值，只做相对形状验证，不是独立标定。该偏置必须用卡尺或平板靠尺独立测得，不能用拟合残差反推。平面拟合的 tilt_deg 不受该偏置影响（所有球心沿同一方向平移不改变法向）；rms_mm/max_dev_mm 描述的是球心线平面度，要报 ribbon 表面平面度需先减掉杆向量。geometry_quality 改为按中位数与超限帧占比判定，避免个别掉点帧触发假警告。

2026-10-16 两端约束重建：10 个侧边 marker 只覆盖带子两侧的观测段，重建不出两个末端。新增 fit_ribbon_full：中轴线从 **ribbon 端面中心**沿**法兰外侧指向**出发（**默认不加刚性直线段**，见下条更正），中段由 10 个 marker 的中线约束，末端落在 **ribbon_end 端面中心**（该资产唯一 marker 沿 Nokov 世界 z 减 25mm），横向仍按卡尺带宽展开，覆盖完整带长而非只有观测段。法兰点由 `flange_track` 给出：读 `trajectory.csv.ribbon_guard` 的 FK 链（base→fer_ribbon_tcp，链末端姿态取局部 axis，默认 z）+ `trajectory.csv` 关节角（帧墙钟 −`execution_started_at` 映射到轨迹时间）+ 外参 `T_world_base`（YAML 4x4，p_world=T@p_base，两侧单位均为米）变到 Nokov 世界系。该模式**必须显式给 `--world-base-extrinsic`**：给了 `docs/RIBBON.md` 早先“尚无外参”的限制才被有条件解除，外参错则整条中轴线跟着错，报告里如实标注来源。缺外参、缺 guard/trajectory、缺 ribbon_end 行或结果里没有 `execution_started_at` 时**不报错**，回落到只拟合观测段，并在 `end_constraints.reason` 写明原因；帧时间落在轨迹窗口外会被夹到端点并单独计数（`outside_trajectory_window`）。报告新增 `reconstruction`、`ribbon_length_m`、`observed_length_m`、`flange_vs_observed_tangent_deg`（校验“法兰外侧指向 = 带子走向”这一假设）、`end_gap_flange_mm`/`end_gap_marker_mm`，`ribbon_fit_diagnostics.json` 里还带 `end_constraints` 元信息。相关参数：`--end-frame-axis`、`--end-frame-offset-m`、`--clamped-length-m`、`--ribbon-end-set`/`--ribbon-end-marker-id`、`--ribbon-end-z-offset-m`、`--trajectory`、`--guard`。链路末端 FK 位置在实测起点上等于 guard 的冻结 X 下限（0.4094m），可用来交叉确认链选对了。

链末端与法兰的换算（2026-10-16 现场确认，已固化成常量并有回归测试）：guard 链是 Franka 标准 modified DH（`d1=0.333, d3=0.316, a4=0.0825, a5=−0.0825, d5=0.384, a7=0.088`）后面两级固定变换——**倒数第二级 `+0.107 m` 就是机器人法兰面**（对应 DH 的法兰偏移），**最后一级 `+0.058 m` 是 ribbon 端面与法兰面之间的 58 mm 连接件**。所以链末端 `fer_ribbon_tcp` 恰好是 **ribbon 端面中心**，`--end-frame-offset-m` 用默认 `0`（**不要**把 0.107 当成“超出法兰”，否则会多算 107mm）。`FLANGE_CONNECTOR_M=0.058` 与 `CLAMPED_LENGTH_M=0.05` 是常量，`fit_ribbon_full`/CLI/报告默认都取它们；`--clamped-length-m` **以 ribbon 端面中心（= 连接件/链末端）为起点**——现场“从法兰算起约 5cm”的实际口径就是从连接件起算，所以直接是 50mm，不需要再减 58mm。回归测试 `test_guard_chain_tip_is_flange_plus_connector` 会用冻结 guard 样本核对这两级偏移，链格式变了会报警。

Nokov↔base 标定（2026-10-16，第二版：两个独立三点刚体）：独立小程序 `tools/world_base_calibrate.py`。**第一版用单个两点资产 `ribbon_mid` 失败**，原因是两点模板只有一条 linkage 约束，而两个端部 marker 跨在**柔性**带子两端——调平过程一拉紧/放松，两端间距就变（实测 1081.0 → 1000.3mm，压缩 7.5%），唯一的约束不满足，整个 set 解不出来，两颗 marker 退化成了未命名点（`source=other`）。现改为**两个三点刚体**（`TemplateType=0`，都含 `Marker1/2/3`、`Size=4` 对应 8mm 球）：**`ribbon_x1` 的 `Marker1` = 远端（静止端）**，**`ribbon_x0` 的 `Marker3` = 近端（法兰端）**。每个 set 内部三点互距恒定（同一夹具），所以 linkage 永远满足、且对整体平移不变——这是它比两点跨软带子稳的根本原因。默认参数就是这两个资产/名字，`--far-end-set/--far-end-marker/--near-end-set/--near-end-marker` 可覆盖；给 `--marker-set` 仍可回到"单一资产里按名字取两端"的旧口径（此时需同时给 `--far-end-marker/--near-end-marker`）。角色**一律按资产+marker 名判定，绝不按世界 x**：实测世界 x 次序与角色相反（`ribbon_x1/Marker1` 在 x 小端），程序把 `world_x_order` 只当事实报出来。录制只对这一次采集加 `--other-markers`（主线采集不受影响）。近端按此顺序取：① `ribbon_x0/Marker3`；② 显式 `--near-end-other-index N`；③ 自动从 `source=other` 的未命名点里挑"到远端距离最接近 `--nominal-length-m`"的那个，必须落在 `--end-distance-min-m/--end-distance-max-m` 窗口内、与次优候选拉开 5cm 以上，否则放弃并降级（绝不硬猜）；结果里如实记 `near_end_source`、`other_points_seen`、`other_fallback_rejected`。实测 `ribbon_x1/Marker1` 与 `ribbon_x0/Marker3` 相距 **1.0001 m**（与标称 1.0m 吻合，第一版的 1.081m 问题随之消失）。于是 `远端端面中心 = 远端 marker − 25mm·ẑ`，`法兰中心(世界) = 近端 marker − 25mm·ẑ − 58mm·â`，`â` 默认取**两端连线方向**（`--connector-axis ribbon`；两端各 25mm 的 z 偏置相减后抵消，所以两 marker 连线就是两端中心连线），也可切现场口径的沿世界 x（`--connector-axis world_x`），程序报出两者夹角与差异（实测 14.0° / 1.9mm）。旋转按现场确认取 `R=diag(-1,-1,1)`（x/y 相反、z 一致），平移 `t = 法兰中心(世界) − R·法兰中心(base)`。机器人侧**只读 franka 状态快照**：`法兰中心(base) = (O_T_EE·F_T_EE⁻¹)[:3,3]`（libfranka 的 16 元素数组是**列主序**、平移在末列；快照里两个矩阵都有，已用冻结 guard 链交叉验证到 1e-3 以内），因此**不需要 FK 链**，也就绕开了"调平时 `trajectory.csv.ribbon_guard` 还不存在"的问题。⚠️ 快照与动捕采集**必须同一静止姿态**，且快照默认限龄 15 分钟（超龄直接拒绝、降级），否则算出来的平移是错的——这也是它必须紧跟在调平之后跑的原因。结果持久化到 `tools/state/world_base.yaml`（含标定时间、输入快照/CSV、两端位置、间距、角色与来源、z/连接件偏置），`pipeline_videos.load_extrinsic` 可直接读。
**2026-10-16 第三版（当前默认）：端点与端部走向全部只从动捕来，不再经过 FK 与外参。** 起因是外参口径实测有系统性偏差：起始绷紧静止段"法兰 z（FK+外参）vs 带子实际走向"差 **12.9°**，而"带子自身直不直"只有 **1.9°** —— 说明偏在机器人/外参一侧。三重交叉验证（局部中轴切向、1m 两端连线、切线基线 1→35 点）都指向同一结论；换 x/y 轴更差（68°/74°），换基线长度无影响。进一步用 `ribbon_x0` 三点组自建坐标系测量：带子走向在该系里 **起始段散度仅 0.26–0.36°（p95 0.7°）**，说明法兰↔夹具↔带子之间存在一个**固定的安装/耦合角**；而这个角与"外参旋转假设的误差"在方向数据上**数学等价、无法分离**（两者复合成同一个固定旋转 `R·M`）。既然分离不了，就不去分离：`pipeline_videos.py` 的端点来源改为 **mode=markers（默认）**——两端面中心分别取 `ribbon_x0/Marker3`、`ribbon_x1/Marker1` 沿世界 z 减 25mm，端部走向在拟合时由"端面中心 → 观测段近端"的连线给出（`fit_ribbon_full(..., flange_axis=None)`，报告里 `end_axis_source=end_centre_to_observed`）。这样那 13° 与 44–55mm 位置残差**按构造消失**，整条重建变成纯动捕。实测对比同一 run（`20261016_235219_06e7f038`）：外参口径重建带长中位 **1.0403m**（p5–p95 0.982–1.046，超出 1m 不合理），纯动捕口径 **0.9858m**（0.956–1.0005，落在松弛↔绷紧的合理区间），宽度残差两者都是 ~0.6mm。新参数：`--end-mode {markers,extrinsic}`（默认 markers）、`--near-end-set/--near-end-marker`（默认 `ribbon_x0/Marker3`）、`--far-end-set/--far-end-marker`（默认 `ribbon_x1/Marker1`）、`--end-z-offset-m`（默认 0.025，两端共用）。`mode=extrinsic` 保留旧口径（近端走 FK+外参、需 `--world-base-extrinsic`）作为交叉验证；标记为 `flange_vs_observed_tangent_deg` 的那个量在 markers 口径下含义变为"端部 0–15cm 弦向 vs 观测局部切向"，即**端部弯曲度**，不再是外参误差指标。标定程序 `tools/world_base_calibrate.py` 与 `tools/state/world_base.yaml` 仍然保留，但**默认拟合不再依赖它们**。

**2026-10-17 更正：这 1m 内没有夹具影响。** ribbon 材料总长超过 1m，被夹具夹住后**暴露的自由段恰好 1m**，夹持段在这 1m 之外。所以 `CLAMPED_LENGTH_M` 由 0.05 改为 **0**（不再在自由段内强制 50mm 直线），`--clamped-length-m` 保留给"夹具确实夹进自由段"的场合。实测该项对结果**无实质影响**：`clamped=0.05` 与 `0.00` 在同批数据上弧长中位都是 0.9864m、宽度残差都是 0.63mm（因为端部走向本就取自数据，带子在那 50mm 里几乎就是直的）。同时新增**自由段长度约束**作为独立质量指标：材料不可伸长 ⇒ 重建弧长应恒等于 `--free-length-m`（默认 1.000m）。`fit_ribbon_full` 每帧报告 `free_length_error_mm = 弧长 − free_length_m`，渲染汇总给 `free_length_error_mm_median/_p5/_p95/_max_abs` 与 `free_length_quality`（`max|偏差| > 30mm` 判 warning，并写 `free_length_warning`）——**它不是运行失败，而是提示端部桥接模型不宜用于量化结论**。实测该 run：中位 **−13.7mm**、p5 −42.7 / p95 +0.5、最大 43.1mm → warning；而**观测段**（10 个 marker 首末之间的固定材料）弧长变化只有 **1.1%**，说明误差集中在两端各约 15cm 的样条桥接段，不是实测段。这个量不依赖机器人/外参，可直接当回归测试用。

**2026-10-17 视频/播放器三件套**：每次 ribbon 渲染**最多**产出三样东西 —— ① `videos/ribbon_fit.mp4`（原样保留：marker 点 + 两侧虚线 + 曲面）；② `videos/ribbon_only.mp4`（**只有带子曲面**：无 marker 点、无虚线、无栅格、无坐标轴，方形 480×480）；③ `videos/ribbon_viewer.html`（**可自由转视角的交互播放器**）。三者共用同一个 `surface_for(frame)`，所以内容严格一致。播放器是**零依赖、自包含**的：环境里没有 plotly/mpld3 且外网不通，所以 `tools/ribbon_viewer.py` 用 canvas 2D + 自写透视投影 + 画家算法（面片按深度排序）绘制，逐帧曲面的顶点数据内联进 HTML，**不需要 CDN、不需要服务器**，浏览器直接打开即可（实测 160 帧/914KB/零外部引用）。交互：左键拖转视角、滚轮缩放、Shift 或右键拖平移、播放/暂停、进度条、0.1×–8× 倍速（播放按每帧真实时间戳推进，1× 即真实时间；相邻关键帧线性插值保持平滑）、复位视角；画面只有 ribbon 本身，没有栅格。**2026-10-20 起默认只生成 ③（HTML）**；① 和 ② 需要 `--ribbon-videos`。开关与抽稀参数：`--ribbon-videos/--no-ribbon-videos`（默认关，开启后才生成 ①/②）、`--clean-video/--no-clean-video`（默认开，仅在 --ribbon-videos 时生效）、`--ribbon-viewer/--no-ribbon-viewer`（默认开）、`--viewer-frames`（默认 160，直接决定 HTML 体积）、`--viewer-samples`（默认 44）、`--viewer-transverse`（默认 5）。

**2026-10-17 观感修正（"看起来像被夹具夹住"）**：现场反馈播放器里带子像被两端夹住/折起来。查下来**不是夹具建模残留**——`clamped=0.05` 与 `0` 的弧长、宽度残差四位小数相同，几何里早就没有刚性段。真正的原因有三个，已全部修掉：① **相机方位几乎顺着带子长轴**（带子方位约 165°、相机 azim −55°，只差 50°），透视强烈缩短把 0.85m 的水平跨度压扁，下垂 200mm 就占了主导，看起来就成了折不明显的 V。现在 `ribbon_azimuth()` 由点云水平主方向算出**垂直于长轴**的方位角，视频与播放器默认都用它；② **面片网格**：`plot_surface` 相邻面片之间的抗锯齿缝会在带子上画出规整网格，像硬板。改为 `antialiased=False, edgecolor="none"`（播放器同时把明暗对比由 0.30–1.00 收到 0.74–1.00）；③ **两端外推段被画得和实测一样**：最后 12–16cm 没有 marker、是样条桥接，画出来像"被夹直"。现在按 `observed_arc_start_m/observed_arc_end_m` 分段，**实测段实色、外推段浅色**（视频与播放器一致），一眼能区分"测到的"和"推出来的"。顺带修掉一个会直接让渲染失败的 bug：用 `np.linalg.svd` 分解整片 `(N,2)` 点云时 numpy 默认 `full_matrices=True` 会分配 `N×N` 的 U（本 run 是 53886² ≈ 21.6 GiB），现改为只分解 2×2 协方差矩阵。也确认了"下垂"本身是真实物理：原始 marker 的 z 跨度全程中位 **268mm**。

**2026-10-17 播放器内置录制**：`ribbon_viewer.html` 工具条新增「**● 录制**」和「**导出当前帧**」。录制用浏览器标准的 `canvas.captureStream()` + `MediaRecorder`：**先把视角调好，点录制，它会从头播一遍并按当前视角整段录制，结束后自动下载**，录制过程中改变视角也会被录进去；录到进度条末尾自动停止（也可点「■ 停止」提前结束）。格式在页面加载时按浏览器能力自动挑选，顺序为 `video/mp4;codecs=avc1` → `video/mp4` → `video/webm;codecs=vp9` → `vp8` → `video/webm`，实际会用什么写在按钮的悬停提示里（Chrome 较新版本直接出 MP4，老一些的浏览器出 WebM）。不支持 `MediaRecorder` 的浏览器会弹提示，可用「导出当前帧 PNG」逐帧保存再 `ffmpeg` 合成。录制画面只含 canvas 上的 ribbon 本身——工具条和 HUD 是 DOM 覆盖层，**不会**被录进视频。边界处理：录制中按暂停或拖进度条会立即结束录制（避免录出一段静止画面且永不停机）。注意这是**浏览器端实时录屏**（分辨率=窗口 canvas 尺寸、码率 12 Mbps），不是离线的逐帧编码；需要无损/固定分辨率时用「导出当前帧」+ `ffmpeg -framerate 20 -i frame_%04d.png out.mp4`。


`run_pipeline` 在 `ribbon_level` 之后立刻调用一次（`Pipeline.run_world_base_calibration`），按读到的 marker **分三种处理**（程序退出码：正常 0、中断 3）：

降级运行（`initial_state_source=default_start_pose_fallback`）没有本次调平测量，**不调用**这个世界系标定，`result.json` 记 `world_base_calibration.status=skipped`。

| 读到 | 处理 |
|---|---|
| 两个都在 | 重新标定并**更新** `tools/state/world_base.yaml` |
| **只有远端 `x0`** | 正常降级：**不覆盖**，沿用上次保存的 `T_world_base`，`result.json` 里记 `warning` |
| **只有近端 `x1`** | **直接中断**：抛 `PipelineError("WORLD_BASE_CALIBRATION_BLOCKED")`，不落盘。远端参考缺失时端点约束重建不成立，硬跑没有意义 |
| 一个都没读到 | 非致命：沿用上次结果 + `warning`（不中断，保持和旧行为一致） |

marker 角色用**资产 + 名字**判定，可用 `--far-end-set/--far-end-marker`（默认 `x0/Marker3`）与 `--near-end-set/--near-end-marker`（默认 `x1/Marker2`）改（2026-10-22 资产改名后的默认值，来历见 18.1 之前的 2026-10-23 段）；两个都在时若"x 最大的那个"不是配置的远端名，会在结果里给 `name_order_warning`，提示带子方向或命名与约定不符、58 mm 连接件的方向假设可能反了。任何非中断的异常都只降级不抛出，**不打断规划与执行**。标定录制落在 `<run>/world_base_calibration/` 子目录，日志 `<run>/world_base_calibration.log`（渲染端的“只有一个 marker CSV”兜底 glob 会排除含 `world_base` 的文件名）。`pipeline_videos.py` 只在 `--end-mode extrinsic` 时用这份保存的外参（默认 `markers`，见上条）；旧资产 `ribbon_mid` 与 `--ribbon-end-set` 参数已移除，`--ribbon-end-pick-x` 仍可按世界 x 从同一资产里挑 max/min，`read_end_point` 在 `pick_x=None` 时对一帧内出现多个匹配行视为歧义并跳过。

两个如实记录的近似：① 连接件的 58 mm 是**沿世界 x** 减的（现场口径），真正方向应沿 ribbon 长轴，程序会报出 `ribbon_axis_vs_world_x_deg` 与由此产生的 `connector_axis_approximation_mm`；② 单点法只有一个点，无法独立验证旋转，所以务必看渲染输出的 `flange_vs_observed_tangent_deg`（应接近 0）和 `ribbon_length_m`（应接近 1.0m）作为交叉检查。相机、机器人底座、端部 marker 支架任一被移动过，都必须重标。

**2026-10-23 端点口径（当前默认）：`x1/Marker2` + `x0/Marker3`，端板法向偏移。** 资产改名后，带身仍由
`ribbon_1021`（12 点）观测，两端改由**端板刚体**锚定：机械臂端 `x1/Marker2`、固定端 `x0/Marker3`，两者都在
带子中心线正上方（高 27.2 / 29.3 mm，横向 1.6 / 1.1 mm），所以 `--end-z-offset-m` 默认 0.028。
`read_end_point` 新增 `--end-offset-mode plate_normal`（默认）——每帧把该资产的全部 marker 与首帧参考位形做
Kabsch 刚体拟合，把 `[0, 0, −z]` 偏移按端板姿态旋转后再叠加，纠正旧口径在带子绕长轴转 180° 后偏 2×z 的
系统误差；缺任一板点或残差 >5 mm 时该帧退回 `world_z`，两种帧数分别记在
`end_constraints.near_end_offset.plate_normal_frames` 与 `.plate_world_z_fallback_frames`，不伪造。
`--end-offset-mode world_z` 保留给旧数据。端板可解性已验证：`x1` 四点 24 种排列的最小残差 28.4 mm
（旧三点几何 10.1 mm），任何会挪动 `Marker2` 的排列残差 ≥28.4 mm、位置错 40–113 mm，端点稳。
`world_base_calibrate` 的默认同步为 `--near-end-set x1 --near-end-marker Marker2` 与
`--far-end-set x0 --far-end-marker Marker3`；`tools/state/world_base.yaml` 仍是 8 mm 时代那份
（`connector_m: 0.008`，记录里是 `ribbon_x0` / `ribbon_x1` 旧名），下一次标定才按新名与新连接件改写。
**未做**：端点扭转插值（把外推段的 director 从未实测段单调过渡到端板滚转），需要一次带完整 180° 扭转的
完整采集才能验证。见 15.6、18.1、18.2。

#### 18.1 远程 GUI 与默认录像

--gui 默认关闭，pro6000 的 extension 不暴露/传递 gui 参数。无头模式使用服务器端离屏渲染，生成 Gazebo 相机画面不需要打开 GUI。若用户直接在远端传 --gui，窗口在 r9000p，不会经 SSH JSON 任务通道显示到 pro6000；可用桌面会话、显示权限与图形驱动是必要条件，缺少时可能显示连接/渲染失败或仿真启动超时。状态与日志仍由任务通道返回；窗口不能反馈不是报错原因。

原生 CLI 与 extension 均默认请求 simulation 录像与 ribbon 后处理；2026-10-20 起 ribbon 后处理默认只生成 videos/ribbon_viewer.html，两个 MP4 不随任务默认生成。显式 videos={simulation:false,ribbon:false} 由网关传为 --no-video --no-ribbon-video；videos.ribbon=true 只表示生成 HTML + 诊断，不表示生成 MP4。网关的显式 render_videos（pro6000: robot_pipeline_render_videos）会在终态任务上补录两个 MP4。不把这些 pipeline 标志传给独立 API runner。mode=plan 不含仿真，ribbon 后处理须有本任务有效采集数据；默认开启不保证每个模式都有 HTML。

**2026-10-20 默认只生成 HTML。** 运动结束后的 ribbon 重建默认只写
`videos/ribbon_viewer.html`、`videos/ribbon.json`、`videos/ribbon_fit_diagnostics.json`；不再逐帧
matplotlib 画 20 fps 的 MP4。需要两个 MP4 时：

```bash
# 任务提交时直接 opt-in（整段后处理会慢约 2 倍运动时长）
python3 tools/run_pipeline.py --task ... --mode execute --ribbon-videos

# 或事后只补渲染已保存数据（不需要机器人/ROS/仿真）
python3 tools/pipeline_videos.py --run-dir pipeline_runs/<run_id> --kind ribbon --ribbon-videos
# 只要标注视频、不要纯带子视频
python3 tools/pipeline_videos.py --run-dir pipeline_runs/<run_id> --kind ribbon --ribbon-videos --no-clean-video
```

`--ribbon-videos` 必须和 `--ribbon-video` 一起用；`--no-ribbon-video` 会关闭整段 ribbon 后处理。
HTML-only 仍会做一次逐帧拟合（20 fps 目标帧，85 s 运动约 12 s），以保证 `ribbon.json` 的质量指标和
`ribbon_fit_diagnostics.json` 不缺失；省掉的是两个视频的逐帧 3D 光栅化和 OpenCV 编码。

#### 18.2 Agent tool 映射

| 文档功能 | extension tools |
|---|---|
| 读取本手册 | read_franka_manual（document=context/api 都返回本文件；section 或 start_line/max_lines；返回 SHA256） |
| 当前机器人状态 | franka_read_state |
| Nokov 资产、有限时长监视、记录 | nokov_list_assets / nokov_monitor / nokov_record |
| marker 分析、会话测量/状态、调平 | ribbon_analyze / ribbon_measure / ribbon_session_status / ribbon_level_run |
| 保存姿态归位、微动、保存 CSV 校验/执行 | franka_home_pose / franka_cartesian_delta_move / franka_execute_offline |
| 完整路径（从结构化参数生成规格） | prepare_robot_pipeline_spec → robot_pipeline_submit → robot_pipeline_start |
| 完整路径（按 r9000p 上已有任务 YAML） | robot_pipeline_list_tasks → prepare_robot_pipeline_remote_task → robot_pipeline_submit → robot_pipeline_start |
| 查看可复用的 plan/prepare 运行 | robot_pipeline_list_runs |
| 从已有 plan/prepare 生成 prepare/execute 复用规格 | prepare_robot_pipeline_from_run → robot_pipeline_submit → robot_pipeline_start |
| 向运行中的提示发送精确答案 | robot_pipeline_confirm |
| 状态、日志、成果、哈希取回 | robot_pipeline_status / robot_pipeline_logs / robot_pipeline_artifacts / robot_pipeline_fetch_result |
| 队列状态（只读） | robot_pipeline_queue_status |
| 暂停/恢复自动启动 | robot_pipeline_queue_pause / robot_pipeline_queue_resume |
| 补认某个排队任务 | robot_pipeline_acknowledge |
| 调整排队顺序 | robot_pipeline_reorder |
| 终态任务视频查询/补录（显式生成两个 ribbon MP4） | robot_pipeline_render_videos |

**2026-10-22 操作者放行不经 extension 工具。** 队列的 `approved` 只能由现场操作者在本机看板或 r9000p 上
执行 `robot_job approve --id <id>` 写入；extension 没有 `robot_pipeline_approve`，远端（pro6000）既不能
代为放行，也不能用提交参数预置放行。`robot_pipeline_acknowledge` 仍只写标定运动确认，默认配置下已不足以让
任务自动启动；`robot_pipeline_queue_status` 如实返回每项的 `approved` 与 `eligible`。

**启真平台 Adapter 2.3.11 源码同步（2026-10-23）。** `adapter.json` 的显式起点标识改为
`flange_58mm_v3`，宽面对齐说明改为法兰外 58 mm；不手工改写旧起点或复用旧安装 CSV/guard。
`src/core.py` 的 `franka.nokov.monitor` / `franka.nokov.record` 固定选择 `--plane ribbon_1021`，
`franka.shape.extract` 只提取 `source=markerset`、`set_name=ribbon_1021` 的有效点，回执也使用新名；
旧 `ribbon` 数据与端板 `x0` / `x1` 不会混入带身单帧点列。pipeline 主路径仍按现场
`ribbon_params.yaml` 取资产名；端点锚定与 `plate_normal` 偏移由原生后处理负责。
`franka.manual.read` 读取随该版本发布的 `docs/RIBBON.md` 副本及其 SHA-256，不实时读取主手册。
相关测试与随包手册一同更新，已完成 AMD64/ARM64 无硬件回归、真实 YAML 解析补测及
Connector/handler/broker 替身烟测；源码更新和生成包不代表安装或生效，本次未切换已安装版本、
未重启 broker、未同步平台能力、未连接或驱动设备。
网关队列及 extension 工具与本 Adapter 是不同入口；本 Adapter 不新增 `approve` 或检查点复用操作。

**三条输入路径不能混用。** `prepare_robot_pipeline_spec` 从结构化参数生成任务规格；`prepare_robot_pipeline_remote_task` 按路径读取 r9000p 上已有的任务 YAML；已有 `plan`/`prepare` 运行用 `prepare_robot_pipeline_from_run`。任务已经是文件时不要用结构化入口重新描述（容易漏字段或改掉语义），已有运行也不要重新提交 task YAML。三条路径最终都经 `robot_pipeline_submit` 登记为同一种不可变任务，再 `robot_pipeline_start` 显式启动；启动仍受运动总开关与串行锁约束，MOVE 提示需用户明确确认，可通过 `robot_pipeline_confirm` 远程发送或 attach 输入。

**复用已有 run 的边界（2026-10-19）。** `robot_pipeline_list_runs` 只读列出 `pipeline_runs` 根或其某个子目录的**当层**运行（不递归），返回 `run_id`、`mode`、`status`、`level` 与可用阶段；清单本身不做全量校验，列出不代表可以复用。`prepare_robot_pipeline_from_run` 接受 `mode=prepare` 或 `mode=execute`，先通过网关 `read_run` 重新校验并哈希源运行的 task/trajectory/guard/result/checkpoint，再把源信息写进新的不可变 `ribbon_hardware_pipeline_resume` 规格；它不接收 task YAML，不复制或改写源运行目录。`robot_pipeline_submit` 对复用规格调用网关 `submit_resume`，只登记普通排队任务，不启动；execute 复用同样进入队列，不需要先单独跑 prepare 步骤。worker 启动前会再次核对源运行复合哈希，源在排队期间被改动则拒绝启动。起点校验仍会执行；`HOME`/`RELEVEL`/`QUIT` 和最终 `MOVE` 由 `robot_pipeline_confirm` 远程发送当前提示列出的精确答案，或由 attach 终端输入，不再要求现场人员。

**远端 YAML 入口的边界（2026-10-22）。** 任务根是 `~/ribbon_ws/trajectories`（网关 `tasks_root`；2026-10-22 前是 `~/ribbon_ws/pipeline/trajectories`）。`robot_pipeline_list_tasks` 列出该根或其中某个子目录当层的 `.yaml/.yml`（不递归；根层传 `.`，空串会被拒绝），返回每个文件的 `task_path`、`bytes`、`sha256`；单文件限 1–2 MiB，每目录最多 200 个，清单本身带 `scientific_evidence: false`，列出文件不代表任务通过校验或可以执行。`prepare_robot_pipeline_remote_task` 用 `task_path` 读取该文件的原始字节并计算 SHA256，只接受任务 YAML（顶层必须是 mapping）；`start_state_file` 只允许指向共享的 `/home/zhaoyunzyq/ribbon_ws/ros/src/franka_motion_planner/config/franka_start_pose.yaml`，网关会按该路径读取这份快照并提供其哈希，指向其它路径会被拒绝。相对路径按 `tasks_root` 解析；绝对路径与符号链接也必须落在该根内，`pipeline/docs/`、`pipeline/tools/` 或 r9000p 上其它目录的文件不能走这个入口，需要先把任务放进 `~/ribbon_ws/trajectories/`（子目录可以，`task_path` 用清单返回的绝对路径）。该工具只读取并准备任务内容，不登记、不启动、不运动、不改写原 YAML；登记由 `robot_pipeline_submit` 完成。除共享起点外，任务引用的其它文件不会被打包，请用绝对路径并自行确认存在。

运动 API 先登记精确任务；tool-agent/tool-chat 在用户明确要求执行后直接调用 robot_pipeline_start，无需 /authorize 或额外独立授权记录。MOVE/HOME/RELEVEL/QUIT 提示由用户明确选择后，通过 robot_pipeline_confirm 发送当前 pending_confirmation 列出的精确答案；该工具不能发送任意按键，也不判断现场是否安全。非运动 API 可自动登记启动，但 FCI 读取仍需独占，测量可能更新会话。已有 tool-chat 窗口需重启一次加载新工具；手册读取每次返回远端当前内容，不依赖本地副本。

2026-10-18 pro6000 交互入口权限更新：按用户要求取消 tool-agent/tool-chat 的额外 /authorize 门槛。启动仍通过原 extensions → Python → 任务网关链路，保留不可变任务输入校验、运动总开关、串行锁和原生 MOVE 提示；正式科研的 Reviewer 与现场授权合同不变。历史授权记录保留为审计；需重启已有交互窗口加载更新，本次变更不启动任何设备。

2026-10-18 修正记录（18.2 映射表）：此前本节只写 `prepare_robot_pipeline_spec → robot_pipeline_submit → robot_pipeline_start`，未列 `robot_pipeline_list_tasks` / `prepare_robot_pipeline_remote_task`，读到“按 YAML 路径执行”会误以为托管工具没有入口。两个工具已在 extension 注册，分别对应网关 2026-10-18 新增的 `list_tasks` / `read_task` 通道；已有 tool-chat 窗口需重启一次加载。本次修改只涉及文档，不登记、不启动、不连接任何设备。

2026-10-19 复用入口更新（同日二次）：网关新增 `list_runs`（只读当层列表）、`read_run`（全量校验并返回复合哈希）、`submit_resume`（`mode=prepare|execute`）与 `send_input`（仅发送当前提示的精确 choice）；pro6000 对应新增 `robot_pipeline_list_runs`、`prepare_robot_pipeline_from_run`、`robot_pipeline_confirm`，并把 `ribbon_hardware_pipeline_resume` 纳入可审批协议。复用规格仍走原 `robot_pipeline_submit`/`robot_pipeline_start`；execute 复用进入队列，运行中的提示可远程确认。已有 tool-chat/tool-agent 窗口需重启一次加载新工具；本次修改不登记、不启动、不连接设备。

**队列工具已封装（2026-10-19 晚）。** `robot_pipeline_submit` 增加可选 `priority`（-1000..1000，高者先，默认 0，只影响排队顺序）；`robot_pipeline_acknowledge` 为某个已登记的 `queued` 任务写入标定运动确认，使其在网关 `auto_start` 开启时可能被队列自动启动。该工具只在宿主手动 tool-chat/tool-agent 上下文可用，正式科研角色仍走 Reviewer 批准 + `robot_pipeline_start`；它不启动任务、不回答任何 pipeline 提示、不证明停稳。`robot_pipeline_confirm` 则在用户明确选择后发送当前提示的精确 choice，不自动代答。`robot_pipeline_queue_pause` / `_resume` 只切换队列的“是否启动新任务”，运行中的任务、其终端与所有人机提示不受影响，也不是急停。`robot_pipeline_queue_status` 只读，返回 `auto_start`、`paused`、当前活动任务、`blocked_by_review` 与按优先级排序的 `queued` 列表（含 `priority`、`acknowledged`、`approved`、`eligible`）。2026-10-22 起新增操作者放行：新任务默认不会自动执行，必须由人在本机队列看板或 `robot_job approve --id <id>` 显式确认后才会进入自动派发。工具源码与 `tool-catalog.json`、`config/tools.yaml` 角色白名单同步更新；已打开的 tool-chat/tool-agent 窗口需重启一次才加载新工具。

#### 18.3 任务队列与自动调度（2026-10-19）

`~/ribbon_ws/robot_gateway` 是 SSH 任务管理层。2026-10-19 起它同时承担
**多任务排序 + 单实例自动派发**：远端可以在任意时间、以任意间隔提交任意多个任务，
网关按队列顺序逐个启动，一次只跑一个。调度器只负责 `queued → starting` 这一步，
不代替人工决策；运行中的 MOVE/HOME/RELEVEL/QUIT 由用户明确选择后经
`robot_pipeline_confirm` 远程发送，或由 attach 输入。`submit_resume` 产生的
prepare/execute 复用任务都是普通 `queued` 任务，同样受 `auto_start`、暂停标志、
`approved`（以及配置开启时的 `acknowledged`）与串行锁约束。

- 程序：`/home/zhaoyunzyq/ribbon_ws/robot_gateway/robot_job.py`，命令包装 `/home/zhaoyunzyq/.local/bin/robot_job`
- 服务：`zd-robot-gateway-queue.service`（`systemctl status|start|stop zd-robot-gateway-queue.service`）
- 状态目录：`/home/zhaoyunzyq/ribbon_ws/Output/`（`jobs.sqlite`、`jobs/`、`config.json`、
  `worker.lock`、`queue.paused`、`execution.lock`、`tmux.sock`）
- 调度日志：`journalctl -u zd-robot-gateway-queue.service -f`，每行一个 JSON
  （`worker_started`、`started`、`wait`、`idle`、`disabled`、`paused`、`blocked`、
  `blocked_needs_review`、`confirmation_timeout_cancel`、`error`；同一 `action`+`job` 连续重复只记一次）

**排序。** `priority` 越大越先（整数 −1000..1000，默认 0）；同优先级按 `created`
先提交先执行。`priority` 只在 `queued` 阶段可改（`robot_job reorder`），
已开始的任务不受影响。`queue_position` 是当前排队位次（1 = 下一个被考虑的任务）。

**自动启动条件（必须全部满足）。**

1. `config.json` 的 `auto_start` 为 `true`（默认 `false`，需管理员显式开启）。
2. `queue.paused` 标志文件不存在。
3. 没有 `starting/running/cancelling/needs_review` 任务。`needs_review` **阻塞整个队列**，
   必须检查（可远程查看状态、日志与录像）后执行
   `robot_job resolve --id <id> --acknowledge-site-check --note "..."` 才解除。
4. 该任务 `approved = 1`。**新提交的任务一律 `approved = 0`，调度器永远跳过**；
   只能由现场操作者显式放行：本机看板 <http://127.0.0.1:8770/> 排队卡片上的
   「确认执行」，或 `robot_job approve --id <id>`（SSH JSON `approve`）。
   提交参数不能预置放行；`approve` 只接受 `queued`，同时写入 `acknowledged = 1`。
5. 默认 `require_submit_ack: true` 时还要求 `acknowledged = 1`。`approve` 会一并写入；
   单独 `robot_job acknowledge`（提交时加 `--acknowledge-calibration-motion`）只记录
   “标定阶段也可能运动”的知情确认，**不再足以让任务自动启动**。
6. 启动前重新校验任务输入、`run_pipeline.py` 与设备配置的哈希；任一变化则该任务
   `failed`，不自动重试。校验和原 `start` 完全共用同一代码路径。

**状态流。** `queued → starting → running → succeeded|failed|cancelled`；
会话丢失、启动握手超时或执行锁不可用会退化为 `needs_review`（不自动重试）。
`awaiting_confirmation` 表示“在等确认”：可 attach 到 tmux 输入，也可用
`robot_pipeline_confirm` 发送当前 `pending_confirmation.choices` 中的精确答案。
它不改变任何权限，也不影响 `needs_review` 的阻塞语义。

**配置字段**（管理员文件 `~/ribbon_ws/Output/config.json`，未知字段会被拒绝）：

| 字段 | 默认 | 说明 |
|---|---|---|
| `auto_start` | `false` | 是否允许调度器自动启动已确认的排队任务 |
| `require_submit_ack` | `true` | 无 `acknowledged` 的任务一律不自动启动 |
| `require_operator_approval` | `true` | 无 `approved` 的任务一律不自动启动；提交无法预置，只能人工放行 |
| `poll_interval_seconds` | `2.0` | 轮询间隔，0.1–60 |
| `confirmation_timeout_seconds` | `0` | `0` = 无限等待人工输入；正数（≤86400）只在 `awaiting_confirmation` 超过该秒数后发 SIGTERM 取消，**绝不代答** |
| `runs_root` | `<workspace>/pipeline_runs` | 可复用 plan/prepare 运行的根；`list_runs` / `read_run` / `submit_resume` 的边界 |
| `tasks_root` | `<workspace>/../trajectories` | 任务 YAML 根（2026-10-22 起为 `~/ribbon_ws/trajectories`）；`list_tasks` / `read_task` 的边界，`health` 会返回 |

当前生产配置为 `auto_start: true`、`require_submit_ack: true`、
`poll_interval_seconds: 2.0`、`confirmation_timeout_seconds: 0`；服务已
`enable --now`，日志只有 `worker_started` / `idle`，没有启动任何任务。

**远端操作**（`--id`/`job_id` 均为任务 uuid，不是 `request_id`）。

| 目的 | CLI | SSH JSON（原有 forced-command key） |
|---|---|---|
| 查看队列 | `robot_job queue --action status` | `{"operation":"queue_status"}` |
| 暂停派发 | `robot_job queue --action pause` | `{"operation":"queue_pause"}` |
| 恢复派发 | `robot_job queue --action resume` | `{"operation":"queue_resume"}` |
| 补认一个排队任务 | `robot_job acknowledge --id <id>` | `{"operation":"acknowledge","job_id":"<id>"}` |
| 放行一个排队任务（唯一自动派发入口） | `robot_job approve --id <id>` | `{"operation":"approve","job_id":"<id>"}` |
| 改排队优先级 | `robot_job reorder --id <id> --priority 5` | `{"operation":"reorder","job_id":"<id>","priority":5}` |
| 提交（可自动启动） | `robot_job submit --request-id <rid> --task <path> --mode prepare --priority 5 --acknowledge-calibration-motion` | `submit` 带 `task_b64`、`priority`、`acknowledge_calibration_motion` |
| 手动启动（旧路径，绕过放行） | `robot_job start --id <id> --acknowledge-calibration-motion` | `{"operation":"start","job_id":"<id>","acknowledge_calibration_motion":true}` |
| 远程确认当前提示 | `robot_job confirm --id <id> --answer MOVE --phase <phase>` | `{"operation":"send_input","job_id":"<id>","answer":"MOVE","expected_phase":"<phase>"}` |
| 人工 attach（可选） | `ssh -t r9000p '... robot_job attach --id <id>'` | — |
| 取消 | `robot_job cancel --id <id>` | `{"operation":"cancel","job_id":"<id>"}` |

**本机队列看板（2026-10-20 新增，2026-10-22 加放行）。** `robot_gateway/queue_dashboard.py` +
`queue_dashboard.html`，用户服务 `zd-robot-gateway-dashboard.service`，地址
<http://127.0.0.1:8770/>（只监听 127.0.0.1）。快照只读（`jobs.sqlite` 以 `mode=ro` 打开）；写操作只有三个、
都只对 `queued` 任务生效、且都委托 `robot_job`：`确认执行`（= `approve`）、`↑` / `↓`（= `reorder`）、
`删除`（= `remove`）。以 `--read-only` 启动时禁用全部写控件。看板不替调度器做决定、不回答问题提示、
不证明停稳，也不是急停。

`queue_status` 返回 `auto_start`、`require_submit_ack`、`require_operator_approval`、
`paused`、`confirmation_timeout_seconds`、`active`、`blocked_by_review`、`queued`
（每项含 `position`、`id`、`request_id`、`mode`、`priority`、`acknowledged`、
`approved`、`age_seconds`、`eligible`）以及恒为 `false` 的 `hardware_stop_verified`。
`health` 也返回 `auto_start`、`require_operator_approval`、`queue_paused`、`runs_root` 与 `tasks_root`。`acknowledge`/`approve`/`reorder`
只接受 `queued` 状态；已开始的任务用 `confirm` 回答当前提示，或用 `attach`/`cancel`。

SSH JSON 提交示例（其余字段同原协议）：

```json
{"operation":"submit","request_id":"exp_0042","mode":"prepare",
 "task_b64":"<base64 任务 YAML>","priority":5,
 "acknowledge_calibration_motion":true}
```

**远程确认与 attach 并存。** 每个任务仍在自己的 tmux 会话中运行；`status` 返回的
`pending_confirmation` 包含当前 `phase`、`prompt`、`choices`，用户明确选择后由
`robot_pipeline_confirm` 发送其中一个精确 choice。网关拒绝未列出的答案、阶段不匹配和
没有活动提示的输入；它不自动确认、不重试、不 `resolve`，也不修改任务输入。
调度器仍只负责“按序把 `queued` 变成 `starting`”；是否执行某一步仍由用户决定。

**部署与回滚。** 服务单元已随代码放在网关目录：

```bash
sudo install -m 0644 /home/zhaoyunzyq/ribbon_ws/robot_gateway/zd-robot-gateway-queue.service \
  /etc/systemd/system/zd-robot-gateway-queue.service
sudo systemctl daemon-reload
sudo systemctl enable --now zd-robot-gateway-queue.service
```

回滚：`sudo systemctl disable --now zd-robot-gateway-queue.service`，再恢复
`robot_job.py` / `ssh_endpoint.py` 的上一版本；数据库新增的 `priority`、
`acknowledged`、`approved` 三列对旧代码无影响。部署前备份在
`~/qizhen-franka-staging/backups/robot_gateway_before_queue_20261019_201410`，
详细部署记录见 `~/ribbon_ws/robot_gateway/DEPLOYMENT.md`，网关自身说明见同目录 `README.md`。

**失败码与处置。**

| 错误 | 含义 |
|---|---|
| `GATEWAY_BUSY: a managed pipeline owns the execution lock` | 另一个进程持有 `execution.lock`；先 `list`/`status` 查清 |
| `GATEWAY_BUSY_OR_REVIEW_REQUIRED: inspect existing job <id>` | 有活动任务或 `needs_review`；后者必须人工 `resolve` |
| `QUEUE_WORKER_ALREADY_RUNNING` | 同一状态目录已有调度器（`worker.lock`），不要重复启动 |
| `REQUEST_CONFLICT: same request-id has different input/configuration` | 同 `request_id` 内容不同；换 id 或原样重提 |
| `Input changed after submission` / `Pipeline or device configuration changed after submission` | 启动前哈希校验失败；重新提交 |
| `Only queued jobs can be acknowledged/approved/reordered` | 任务已开始或已终态；改用 `confirm`/`attach`/`cancel` |
| `NO_PENDING_CONFIRMATION` | 当前没有活动提示；先 `status` 查看 `pending_confirmation` |
| `PHASE_MISMATCH` | `expected_phase` 与当前提示阶段不一致；重新查询后再答 |
| `ANSWER_NOT_ALLOWED` | 答案不在当前 `pending_confirmation.choices` 中；网关拒绝任意按键 |
| `JOB_SESSION_MISSING` | 任务记录为活动但 tmux 会话已丢失；检查日志并 `resolve`/`cancel` |

**安全边界与已知限制。**

- `hardware_stop_verified` 恒为 `false`。`pause`、`cancel`、`systemctl stop` 都**不是**
  物理急停或停稳证明；真实安全仍靠现场与硬件急停。
- `pause` / `systemctl stop` 只阻止**新**任务；正在 tmux 中运行的 pipeline 不受影响，
  需要 `cancel`（SIGTERM 清理）或现场急停。
- 队列不并发、不重试、不自动恢复 `needs_review`；异常一律停在终态或 `needs_review`。
- 迁移前遗留的 `queued` 任务 `acknowledged = 0`、`approved = 0`，不会被自动启动。
  当前两条遗留任务 `pi_pilot_E1A_D060_20261018`、
  `pi_base_z10_x_steps_rotations_v2_20261013` 保持未确认、未放行，需要时人工 `approve`
  （放行并同时记录确认）或 `cancel`。
- pro6000 的 extension 已封装队列操作（2026-10-19 晚）：`robot_pipeline_queue_status`、
  `robot_pipeline_queue_pause` / `_resume`、`robot_pipeline_acknowledge`、`robot_pipeline_reorder`，
  且 `robot_pipeline_submit` 可带 `priority`。`robot_pipeline_submit` 默认仍不写
  `acknowledged`，所以即使 `auto_start=true` 也不会自动开始；要自动排队须在手动控制台显式
  `robot_pipeline_acknowledge`（仅 `queued` 任务，仅手动上下文）。两条遗留任务仍保持未确认。
  已打开的 tool-chat/tool-agent 窗口需重启一次加载；重启与工具调用都**不**启动任何设备。
  2026-10-22 起放行只能由现场操作者在本机看板或 `robot_job approve` 完成，extension 不提供
  `robot_pipeline_approve`；`robot_pipeline_acknowledge` 只写知情确认，不再足以自动启动。
- 同一账号可用不同 `--root` 启动第二个网关，会绕过跨进程 `execution.lock` 造成并发执行；
  不要在生产状态目录之外另起实例。
- 本功能不改变 pipeline 的调平、采集、仿真与视频行为，也不新增运动期间 Nokov 或 ATI 采集。

**验证。** 生产目录 `python3 -m unittest discover -s tests -v` 共 44 项：41 通过，3 项 resume 相关既有失败
（`test_gateway.test_resume_prepare_and_execute_use_from_run_argv`、`test_queue.test_resume_spec_without_inputs_reaches_launch`、
`test_ssh_endpoint.test_resume_rpc_accepts_prepare_and_execute_and_rejects_bad_fields`；都是 `submit_resume`
参数/mock 签名与代码不一致，2026-10-22 12:39 之前即存在，与本次改动无关）。覆盖队列派发、操作者放行、
远程精确确认、execute/prepare 复用、RPC 白名单与旧边界回归；全部使用 `/tmp` 独立状态目录与纯 Python 模拟
pipeline，不导入 ROS、libfranka 或 Nokov，也不连接设备。

