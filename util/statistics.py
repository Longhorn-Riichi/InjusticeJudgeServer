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

# async def test_redis():
#     global redis_client
#     # Increment counters
#     redis_client.hincrby("statistics", "count_a", 1)
#     redis_client.hincrby("statistics", "count_b", 1)
#     redis_client.hincrby("statistics", "count_c", 1)

#     # Get a specific counter value
#     count_a_value = redis_client.hget("statistics", "count_a")
#     print(f"The current value of count_a is: {count_a_value.decode("utf-8")}")

#     # Get all counters
#     all_counters = redis_client.hgetall("statistics")
#     all_counters_decoded = {k.decode("utf-8"): int(v.decode("utf-8")) for k, v in all_counters.items()}
#     print("All counters:", all_counters_decoded)

# # asyncio.run(test_redis())
