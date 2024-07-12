import asyncio
import dotenv
import os
import re
from util.gateway import Gateway
from util.statistics import Statistics
from quart import Quart, jsonify, request
from InjusticeJudge.injustice_judge.fetch.majsoul import MahjongSoulAPI, parse_majsoul, MahjongSoulAPI
from InjusticeJudge.injustice_judge.fetch.tenhou import parse_tenhou
from InjusticeJudge.injustice_judge.fetch.riichicity import RiichiCityAPI, parse_riichicity
from InjusticeJudge.injustice_judge.injustices import format_result, get_results
from typing import *

app = Quart(__name__)
gateway: Optional[Gateway] = None
statistics = Statistics()
majsoul_regex = r"https://mahjongsoul.game.yo-star.com/\?paipu=([a-z0-9]{6}-[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12})(_a\d+)?(_[0-3])?"
tenhou_regex = r"https://tenhou.net/0/\?log=(\d{10}gm-[0-9a-f]{4}-\d{4,}-[0-9a-f]{8})(&tw=\d+)?"
riichicity_regex = r"[a-z0-9]{20}(@.+)?"

@app.route('/injustice', methods=['POST'])  # type: ignore[type-var]
async def run_injustice() -> None:
    await call({"injustice"})

@app.route('/skill', methods=['POST'])  # type: ignore[type-var]
async def run_skill() -> None:
    await call({"skill"})

async def call(look_for: Set[str] = {"injustice"}):
    global gateway
    global statistics
    assert gateway is not None
    data = await request.get_json()
    link = data['link']
    print(link)
    for regex, fetch, parse in [(majsoul_regex, gateway.fetch_majsoul, parse_majsoul),
                                (tenhou_regex, gateway.fetch_tenhou, parse_tenhou),
                                (riichicity_regex, gateway.fetch_riichicity, parse_riichicity)]:
        if re.match(regex, link) is not None:
            try:
                log, metadata, player = await fetch(link)
            except: # try it again
                log, metadata, player = await fetch(link)
            kyokus, parsed_metadata, parsed_player_seat = parse(log, metadata, None)  # type: ignore[operator]
            break
    else:
        raise Exception("Invalid input")

    player = parsed_player_seat if parsed_player_seat is not None else player
    if player is None:
        try:
            all_results = [get_results(kyoku, {0,1,2,3}, look_for) for kyoku in kyokus]
        except:
            all_results = [get_results(kyoku, {0,1,2}, look_for) for kyoku in kyokus]
    else:
        all_results = [get_results(kyoku, {player}, look_for) for kyoku in kyokus]
    statistics.process_game_injustices(all_results)
    return [format_result(seat, result_list, parsed_metadata.name, len(results) == 1)
            for results in all_results
            for seat, result_list in results.items()
            if len(result_list) > 0]

async def run():
    dotenv.load_dotenv("config.env")
    async with MahjongSoulAPI(mjs_username=os.getenv("ms_username"), mjs_password=os.getenv("ms_password"), mjs_uid=os.getenv("ms_uid"), mjs_token=os.getenv("ms_token")) as ms_api:
        print("Logged into Mahjong Soul!")
        async with RiichiCityAPI("aga.mahjong-jp.net", os.getenv("rc_email"), os.getenv("rc_password")) as rc_api:
            print("Logged into Riichi City!")
            global gateway
            gateway = Gateway(ms_api=ms_api, rc_api=rc_api)

            from hypercorn.asyncio import serve
            from hypercorn.config import Config
            config = Config()
            config.bind = ["0.0.0.0:5111"]
            await serve(app, config)

if __name__ == '__main__':
    print(asyncio.run(run()))

    
