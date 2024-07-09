from InjusticeJudge.injustice_judge.injustices import CheckResult
from typing import *

class Statistics:
    def __init__(self) -> None:
        import dotenv
        import os
        import redis
        dotenv.load_dotenv("config.env")
        self.client = redis.Redis(
            host=os.getenv("redis_host"),
            port=os.getenv("redis_port"),
            password=os.getenv("redis_password"),
            ssl=True)

    def process_game_injustices(self, all_results: List[Dict[int, List[CheckResult]]]):
        self.client.hincrby("statistics", "total_games", 1)
        self.client.hincrby("statistics", "total_kyokus", len(all_results))
        for result in all_results:
            for seat, injustices in result.items():
                for injustice in injustices:
                    self.client.hincrby("statistics", "injustice_" + injustice.identifier, 1)
