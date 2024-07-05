import asyncio
import dotenv
import os
import re
from util.gateway import Gateway
from quart import Quart, jsonify, request
from InjusticeJudge.injustice_judge.fetch.majsoul import parse_majsoul, MahjongSoulAPI
from InjusticeJudge.injustice_judge.fetch.tenhou import fetch_tenhou, parse_tenhou
from InjusticeJudge.injustice_judge.fetch.riichicity import RiichiCityAPI, parse_riichicity
from InjusticeJudge.injustice_judge.injustices import evaluate_game

app = Quart(__name__)
gateway = None
majsoul_regex = r"https://mahjongsoul.game.yo-star.com/\?paipu=([a-z0-9]{6}-[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12})(_a\d+)?(_[0-3])?"
tenhou_regex = r"https://tenhou.net/0/\?log=(\d{10}gm-\d{4}-\d{4}-[0-9a-f]{8})(&tw=\d+)?"
riichicity_regex = r"[a-z0-9]{20}(@.+)?"

@app.route('/injustice', methods=['POST'])
async def run_injustice():
    data = await request.get_json()
    link = data['link']
    print(link)
    if re.match(majsoul_regex, link) is not None:
        majsoul_log, metadata, player = await gateway.fetch_majsoul(link)
        kyokus, parsed_metadata, parsed_player_seat = parse_majsoul(majsoul_log, metadata, None)
    elif re.match(tenhou_regex, link) is not None:
        tenhou_log, metadata, player = fetch_tenhou(link)
        kyokus, parsed_metadata, parsed_player_seat = parse_tenhou(tenhou_log, metadata, None)
    elif re.match(riichicity_regex, link) is not None:
        riichicity_log, metadata, player = await gateway.fetch_riichicity(link)
        kyokus, parsed_metadata, parsed_player_seat = parse_riichicity(riichicity_log, metadata, None)
    else:
        raise Exception("Invalid input")
    player = parsed_player_seat or player
    if player is None:
        try:
            return [result for kyoku in kyokus for result in evaluate_game(kyoku, {0,1,2,3}, parsed_metadata.name)]
        except:
            return [result for kyoku in kyokus for result in evaluate_game(kyoku, {0,1,2}, parsed_metadata.name)]
    else:
        return [result for kyoku in kyokus for result in evaluate_game(kyoku, {player}, parsed_metadata.name)]

async def run():
    dotenv.load_dotenv("config.env")

    # mjs_username=USERNAME, mjs_password=PASSWORD
    MS_USERNAME = os.environ.get("ms_username")
    MS_PASSWORD = os.environ.get("ms_password")

    RC_EMAIL = os.getenv("rc_email")
    RC_PASSWORD = os.getenv("rc_password")

    async with RiichiCityAPI("aga.mahjong-jp.net", RC_EMAIL, RC_PASSWORD) as rc_api:
        async with Gateway(rc_api=rc_api, mjs_username=MS_USERNAME, mjs_password=MS_PASSWORD) as g:
            global gateway
            gateway = g
            await gateway.login()
            print("logged in!")

            from hypercorn.asyncio import serve
            from hypercorn.config import Config
            config = Config()
            config.bind = ["0.0.0.0:5111"]

            await serve(app, config)

if __name__ == '__main__':
    print(asyncio.run(run()))

    
