import asyncio
import dotenv
import os
from util.gateway import Gateway
from quart import Quart, jsonify, request
from InjusticeJudge.injustice_judge.fetch.majsoul import parse_majsoul, MahjongSoulAPI
from InjusticeJudge.injustice_judge.injustices import evaluate_game

app = Quart(__name__)
gateway = None

MS_CHINESE_WSS_ENDPOINT = "wss://gateway-hw.maj-soul.com:443/gateway"
MS_ENGLISH_WSS_ENDPOINT = "wss://mjusgs.mahjongsoul.com:9663/"

@app.route('/injustice', methods=['POST'])
async def run_injustice():
    data = await request.get_json()
    link = data['link']
    kyokus, parsed_metadata, parsed_player_seat = parse_majsoul(*(await gateway.fetch_majsoul(link)))
    return [result for kyoku in kyokus for result in evaluate_game(kyoku, set(), parsed_metadata.name)]

async def run():
    dotenv.load_dotenv("config.env")

    # mjs_username=USERNAME, mjs_password=PASSWORD
    USERNAME = os.environ.get("ms_username")
    PASSWORD = os.environ.get("ms_password")

    # mjs_uid=UID, mjs_token=TOKEN
    # UID = os.environ.get("ms_uid")
    # TOKEN = os.environ.get("ms_token")

    async with Gateway(mjs_username=USERNAME, mjs_password=PASSWORD) as g:
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

    
