"""爬虫模块。

包含游戏信息爬虫和评价历史爬虫。
"""

from steam_scraper.scrapers.game_scraper import GameScraper
from steam_scraper.scrapers.review_scraper import ReviewScraper

__all__ = ["GameScraper", "ReviewScraper"]
