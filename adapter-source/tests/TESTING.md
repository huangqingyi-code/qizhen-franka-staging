# 无硬件回归测试

测试使用临时目录、厂商替身、假 Connector 和假 systemctl。没有挂载真实设备工作区。

已有 Linux Edge 测试镜像可按以下方式运行；镜像需具备 Python 3.12、jsonschema 和 rfc8785。
以下仅在一次性容器运行，不连接真实工作区。Connector 源码以平台仓库
`apps/linux-edge-runtime` 为准；不使用设备端从旧 wheel 恢复的源码。
在 staging 的父目录执行：

```bash
docker run --rm --network none --platform linux/amd64 \
  --entrypoint python -v "$PWD:/work:ro" -w /work/adapter-source \
  qizhen-linux-edge-check:amd64 -m unittest discover -s tests -p 'test_*.py' -v

```

平台仓库的 `make linux-edge-check` 和 `make linux-edge-container-check`
验证 Connector 源码与两种架构的正式 wheel。自动上传闭环测试位于
`apps/platform-api/tests/test_artifact_delivery.py`，使用隔离 PostgreSQL、MinIO
和 testkit 产物协议替身，并覆盖接收分片后丢失回执、重启、校验失败与任务关联。

部署机的原生补充测试仍可通过 bash scripts/test.sh 执行。
这些测试不证明真实 ROS、Gazebo、摄像头、ATI 网络、机器人起点或真实运动已通过。
实际设备验证必须作为另一个明确授权的任务执行。

2.3.13 手册入口回归覆盖源码及安装包内 `AGENT_OPERATIONS.md` 的定位、文件名、
版本、分页和 SHA-256，拒绝缺失或空的 Agent 手册，不回退到旧参考手册。
发布包同时包含 Agent 手册与 `RIBBON.md`，修改 Agent 手册后不能复用旧包。

目标架构下的真实 Connector/handler/broker 烟测（只用厂商替身）：

```bash
docker run --rm --network none --platform linux/amd64 \
  --entrypoint python -v "$PWD:/work:ro" -w /work/adapter-source \
  qizhen-linux-edge-check:amd64 tests/connector_smoke.py
```

烟测只在一次性测试容器中运行，要求容器用户 HOME 可写且不存在真实 Adapter 配置。
真实 YAML 解析用已有包含 PyYAML 的平台容器补测；Connector 自身无需新增 PyYAML 依赖。

本版新增回归：pipeline 拒绝检查点复用参数；同一任务的两个新会话各自启动厂商流程、
生成独立轨迹和仿真视频；相同 request_id 重试不重复启动。源录像已经存在时补录仍重新生成，
源输入和回执保持原样；本次生成失败返回 unavailable，不返回旧录像。

## 2.3.11 定向回归

- 显式起点使用 flange_58mm_v3 时原样保存；缺失、flange_8mm_v2 和其它无效标识在创建前拒绝。
- Nokov monitor/record 传 ribbon_1021，list 不增加 plane 参数。
- 形状提取只读取 ribbon_1021 的有效带身点，不混入旧资产、端板或 rigidbody 数据；
  不足两点时回退到最后有效帧，只有旧资产的输入明确失败，不自动改名。
- 随包手册包含 2026-10-23 更新，仍与现场手册路径隔离，保留分页与 SHA-256 检查。

这些检查使用临时输入及厂商替身，不验证真实装夹、标定或运动。
