# kb-tool

统一知识库管理工具，替代散落在 skill references/ 里的 5+ 个 Python 脚本。

## 安装

```bash
cd ~/code/kb-tool
pip install -e .
```

## 命令

```
kb stats              # 快速统计
kb scan               # 扫描断链
kb scan -o report.md  # 扫描并写报告
kb scan --json        # JSON 输出
kb orphan             # 分析孤立文件
kb orphan --by-dir    # 按目录分组
kb fix-zero           # 为零链接文件添加关联
kb fix-zero --dry-run # 预览
kb fix-pipe [file...] # 修复管道符污染
kb sync               # 同步 README 文件计数
kb graph              # 图谱分析 (全部)
kb graph -m hubs      # 枢纽节点
kb graph -m islands   # 孤岛检测
kb graph -m wanted    # 被引用但不存在的页面
```

## 环境变量

- `KB_ROOT`: 知识库根目录 (默认 `~/code/knowledge`)

## 依赖

- click: CLI 框架
- networkx: 图算法
- pyyaml: YAML frontmatter (预留)
