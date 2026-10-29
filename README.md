# 团委工作小工具集

> 个人开发的、给学校团委日常事务用的小工具集合。**非官方项目**，与大鱼等任何组织无关。
> 每个工具都是独立的文件夹，可以单独拿走用，也可以拿去改。

做这些东西的起因很朴素：团委每年要往老系统里补几百个文件、整理几百份材料，
这些活都能用脚本干掉。既然写都写了，就开源出来，别人不用重造一遍。

---

## 工具列表

| 工具 | 用途 | 入口 | 依赖 |
|---|---|---|---|
| [archive-uploader](tools/archive-uploader/) | 老式 ASP 档案系统的批量附件上传：题名配对、演练/断点续传、按文件大小对账体检、自动清理旧附件 | `tools/archive-uploader/开始.bat` | Python 3.8+，零第三方库 |

> 每个工具目录里都有自己的 `README.md`，写清了怎么配、怎么跑、踩过哪些坑。

---

## 仓库结构约定

```
.
├─ README.md                 ← 你在这里：总索引
├─ LICENSE
├─ .gitignore / .gitattributes
└─ tools/
   └─ archive-uploader/      ← 一个工具一个文件夹
      ├─ README.md           ← 这个工具自己的说明（详细版）
      ├─ DeepSeek.md         ← 它是怎么被做出来的（过程记录）
      ├─ 开始.bat            ← 双击就能用的入口
      ├─ config.example.json ← 配置模板，复制成 config.json 再改
      ├─ scripts/            ← 代码
      ├─ docs/               ← 截图
      └─ 样例/               ← 可以先跑通流程的样例数据
```

**根目录只放仓库级的东西**（索引、协议、忽略规则）。具体工具的代码、配置、文档全部收在
`tools/<工具名>/` 里，互不干扰。

### 加一个新工具

```bash
mkdir -p tools/新工具名
# 把代码、README.md、config.example.json 放进去
git add tools/新工具名
git commit -m "feat: add 新工具名"
```

然后回到这个 README 的表格里加一行。

---

## 关于配置与隐私

所有工具都遵循同一条规矩：**真实配置不进仓库**。

- 仓库里只放 `config.example.json`（占位符）
- 真实的内网地址、姓名、密码放在 `config.json`，已被 `.gitignore` 排除
- 运行产物（日志、清单、报告）在 `输出/`，同样不进仓库

如果你 fork 之后要提交改动，请先 `git status` 确认没有把自己的 `config.json` 带上去。

---

## 许可

[MIT](LICENSE) —— 随便用、改也行，不承担任何责任。
