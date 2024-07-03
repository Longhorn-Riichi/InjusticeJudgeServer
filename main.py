import asyncio
import dotenv
import os
from util.gateway import Gateway
from quart import Quart, jsonify, request
from InjusticeJudge.injustice_judge.fetch.majsoul import parse_majsoul, MahjongSoulAPI
from InjusticeJudge.injustice_judge.injustices import evaluate_game

app = Quart(__name__)
gateway = None

@app.route('/injustice', methods=['POST'])
async def run_injustice():
    data = await request.get_json()
    link = data['link']
    kyokus, parsed_metadata, parsed_player_seat = parse_majsoul(*(await gateway.fetch_majsoul(link)))
    try:
        return [result for kyoku in kyokus for result in evaluate_game(kyoku, {0,1,2,3}, parsed_metadata.name)]
    except e:
        return [result for kyoku in kyokus for result in evaluate_game(kyoku, {0,1,2}, parsed_metadata.name)]

async def run():
    dotenv.load_dotenv("config.env")
    # USERNAME = os.getenv("ms_username")
    # PASSWORD = os.getenv("ms_password")
    # UID = os.getenv("ms_uid")
    # TOKEN = os.getenv("ms_token")
    UID = os.environ.get("test_mjs_uid")
    TOKEN = os.environ.get("test_mjs_token")

    async with Gateway("wss://mjusgs.mahjongsoul.com:9663", mjs_uid=UID, mjs_token=TOKEN) as g:
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

    
