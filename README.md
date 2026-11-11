# 🎯 秋招 AI 看板

一个可以自己部署、浏览器打开即用的秋招管理工具。手机和电脑都能访问。

**能做什么**

| 模块 | 说明 |
|---|---|
| JD 解析 & 岗位库 | 粘贴岗位 JD → 豆包自动解析成结构化字段 → 存库；看板视图 / 列表视图，随时改投递状态（待投递 / 已投递 / 测评 / 面试 / 挂） |
| 个人求职档案 | 学历、专业、毕业年份、已掌握技术、薄弱技术、项目、面试记录、长期备注，可手动编辑，也能用语音增量更新 |
| 语音上传 ASR | 上传 wav / mp3 → 火山引擎一句话识别转文字 → 一键「更新档案」或「生成今日计划」，计划存库可回看历史 |
| 岗位 RAG 分析 | 结构化 JD + 个人档案 + 知识库检索结果 → 匹配分（0-100）、优势、短板、3 天学习计划、投递建议，并展示检索到的资料原文 |
| RAG 知识库 | 上传 txt / md 八股、面经、技术笔记，自动切片进 Chroma 向量库 |

---

## 一、项目结构

```
qiuzhao-ai-kanban/
├── app.py              # 主程序：页面、5 个 Tab、交互逻辑
├── llm_client.py       # 豆包（火山方舟）调用 + 强制 JSON 解析
├── asr_client.py       # 火山引擎一句话识别
├── rag_client.py       # Chroma 向量库：切片、入库、检索
├── db.py               # SQLite：岗位 / 档案 / 计划 / 知识库原文
├── prompts.py          # 四套提示词（想换文案只改这里）
├── config.py           # 密钥读取（.env 与 Streamlit Secrets 通用）
├── requirements.txt    # 依赖清单
├── .env.example        # 密钥模板
└── .gitignore
```

运行时会自动生成 `data/` 目录，里面是 `qiuzhao.db`（SQLite）和 `chroma/`（向量库）。

---

## 二、准备密钥（两个服务，共 4 个值）

### 1. 火山方舟（豆包大模型）

1. 打开 <https://console.volcengine.com/ark>，用手机号注册 / 登录，完成实名。
2. 左侧「API Key 管理」→ 创建 API Key → 复制，这就是 `ARK_API_KEY`。
3. 左侧「在线推理」→ 创建推理接入点，模型选 doubao-pro（或你账号下可用的 pro 版本）→ 创建后复制接入点 ID（形如 `ep-2024xxxxxxxx-xxxxx`）。
   把这个 ID 填到 `ARK_MODEL` 里最稳妥（直接填模型名 `doubao-pro-32k` 有时会报模型不存在）。
4. 接入点是「开通即用」，但请确认账户里有免费额度或已充值，否则会提示额度不足。

### 2. 火山引擎语音识别

1. 打开 <https://console.volcengine.com/speech>，进入「语音技术」控制台。
2. 「应用管理」→ 创建应用 → 复制 **APP ID**，填到 `VOLC_APP_ID`。
3. 在该应用下复制 **Access Token**，填到 `VOLC_ACCESS_KEY`。
4. 确认这个应用已开通「一句话识别」能力（没开通会返回鉴权或权限错误）。

> 说明：一句话识别适合 **60 秒以内** 的清晰录音（16k 采样率效果最好）。太长的录音请先截短再上传。

---

## 三、本地跑起来（可选，但强烈建议先跑通再部署）

要求 Python **3.10 ~ 3.12**（3.13/3.14 上 chromadb 可能装不上）。

```bash
cd qiuzhao-ai-kanban

# 1. 建虚拟环境
python3 -m venv .venv
source .venv/bin/activate        # Windows 用 .venv\Scripts\activate

# 2. 装依赖（第一次会下载 torch，约几百 MB，耐心等）
pip install -r requirements.txt

# 3. 配置密钥
cp .env.example .env
# 用文本编辑器打开 .env，把 4 个值换成自己的

# 4. 启动
streamlit run app.py
```

浏览器会自动打开 `http://localhost:8501`。左侧边栏会显示「密钥已配置」的绿字，看到就说明配好了。

---

## 四、部署到 Streamlit Community Cloud（免费，手机电脑都能访问）

### 第 1 步：注册 GitHub

1. 打开 <https://github.com> → 右上角 **Sign up**。
2. 填邮箱、密码、用户名，完成邮箱验证。免费账号就够用。

### 第 2 步：建一个仓库

1. 登录后点右上角 **+** → **New repository**。
2. **Repository name** 填 `qiuzhao-ai-kanban`。
3. 选 **Public**（公开仓库部署最省事；私有可能需要额外授权）。
4. 不要勾选 README（避免和你本地的文件冲突，勾了也没关系）。
5. 点 **Create repository**。

### 第 3 步：把代码传上去（不用命令行）

1. 在新仓库页面，点 **uploading an existing file** 这个链接。
2. 把项目里**除 `data/`、`.env`、`__pycache__` 之外**的所有文件拖进去：
   `app.py`、`llm_client.py`、`asr_client.py`、`rag_client.py`、`db.py`、`prompts.py`、`config.py`、`requirements.txt`、`.env.example`、`.gitignore`、`README.md`。
3. 下方 **Commit changes** 点一下，文件就进仓库了。

> ⚠️ 千万别把 `.env` 传上去——那是明文密钥。代码里已经靠 Secrets 读取，不需要 `.env`。

（会用命令行的话，也可以 `git init` → `git add .` → `git commit` → `git remote add origin ...` → `git push`，效果一样。）

### 第 4 步：注册 Streamlit 并部署

1. 打开 <https://share.streamlit.io> → **Continue with GitHub** → 授权登录。
2. 点 **Create app** / **New app**，选择 **Deploy a public app from GitHub**。
3. 依次填：
   - **Repository**：`你的用户名/qiuzhao-ai-kanban`
   - **Branch**：`main`
   - **Main file path**：`app.py`
   - **App URL**：可以自定义一个前缀，比如 `qiuzhao-kanban`
4. 点 **Advanced settings…**：
   - **Python version** 选 `3.11`（推荐）。
   - **Secrets** 文本框里粘贴下面这段（TOML 格式，等号两边有空格，值用英文双引号）：

```toml
ARK_API_KEY = "你的方舟_API_Key"
ARK_MODEL = "ep-2024xxxxxxxx-xxxxx"
VOLC_APP_ID = "你的语音应用_APP_ID"
VOLC_ACCESS_KEY = "你的语音_Access_Token"
VOLC_ASR_CLUSTER = "volcengine_input_common"
```

5. 点 **Deploy**。首次部署需要装 torch + 向量模型，一般 **5~10 分钟**，页面会显示 "Your app is in the oven"。
6. 部署完成后拿到地址，形如 `https://qiuzhao-kanban-xxxx.streamlit.app`。

**手机访问**：把这个链接发到手机上，浏览器直接打开就行，不用装 App。手机上建议横屏或直接看「列表视图」，看板的五列在窄屏上会比较挤。

### 第 5 步：以后改代码怎么更新

在 GitHub 网页上直接编辑文件 → Commit → Streamlit Cloud 会自动重新部署（约 1~2 分钟）。也可以在 App 页面右上角菜单点 **Reboot app** 手动重启。

要改密钥：App 页面右上角 **⋮** → **Settings** → **Secrets**，改完保存，应用会自动重启。

---

## 五、必须知道的三个限制

1. **数据是临时的**。免费版容器的磁盘在重启 / 重新部署 / 长时间无人访问后会被重置，`data/qiuzhao.db` 里新增的岗位会丢。所以每次录完重要内容，点左侧边栏「**下载数据备份**」存一份到自己电脑。
2. **首次操作会慢**。第一次进知识库 / 第一次做 RAG 分析时，会下载 `BAAI/bge-small-zh-v1.5` 向量模型（约 100MB），要等一会儿，之后就走缓存了。
3. **免费额度有限**。方舟和语音识别都按调用计费，免费额度用完后需要充值。一次 RAG 分析大约消耗一次对话调用。

---

## 六、常见问题

| 现象 | 原因与办法 |
|---|---|
| 部署时报 `ModuleNotFoundError` | `requirements.txt` 没传上去，或者文件名不对（必须是根目录的 `requirements.txt`） |
| 一直卡在 installing | torch 体积大，正常要几分钟，等就是了；超过 15 分钟建议 Reboot app |
| 侧边栏红字「缺少 ARK_API_KEY」 | Secrets 没填或键名拼错；键名必须和 `.env.example` 完全一致 |
| 调用方舟返回 401 | API Key 复制错了（多了空格或换行） |
| 调用方舟返回 404 / 模型不存在 | `ARK_MODEL` 要填推理接入点 ID（`ep-` 开头），不要填模型名 |
| 语音识别返回 code≠0 | 应用没开通「一句话识别」；或音频超过 60 秒、采样率过低、全是静音 |
| 分析结果里参考资料为空 | 知识库里还没有文档，先去第五个 Tab 上传 txt/md |
| 上传中文文档后搜不到 | 文件编码不是 UTF-8 时已自动按 GBK 尝试；仍然异常就另存为 UTF-8 再传 |
| 手机打开显示空白 | 首次加载慢，刷新一次；确认用的是 `https` 开头的 `.streamlit.app` 域名 |

---

## 七、想改提示词 / 改功能

- **改 AI 行为**：只动 `prompts.py`。四套提示词分别对应 JD 解析、岗位分析、档案更新、计划生成，改完重启即可生效。
- **改评分口径**：`prompts.py` 里 `JOB_ANALYZE_SYSTEM` 关于 `match_score` 的那段。
- **换向量模型**：在 Secrets 里加 `EMBED_MODEL = "BAAI/bge-base-zh-v1.5"`（更大更准，也更快吃内存）。
- **本地存哪里**：环境变量 `DATA_DIR` 可改数据目录，`CHROMA_DIR` 可改向量库目录。
