## 工作流程

### 步骤 1: 基础信息抓取

basic_scraper.py 首先抓取 Steam 商店页面上的基础信息。对于每一款游戏，它会获取每个游戏的以下信息并将其保存到一个.xlsx文件中：

- 游戏的 app_id
- 游戏名称
- 发行日期
- 游戏价格
- 开发商、发行商
- 游戏标签
- 游戏简介

同时，basic_scraper.py 会将所有抓取到的 app_id 通过保存为 steam_appids.txt ，供后续使用。

### 步骤 2: 评价信息抓取

在 basic_scraper.py 完成基础信息抓取并保存后，运行 recommendations_scraper.py 进行评价统计信息获取：

- recommendations_scraper.py 会读取 basic_scraper.py 生成的 steam_appids.txt。
- 对于每个 app_id，它会发送请求，获取该游戏的评价信息统计，包括日期及其对应的好评和差评的数量。

