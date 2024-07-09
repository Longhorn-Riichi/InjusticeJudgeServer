import asyncio
import hashlib
import hmac
import logging
import requests
import re
import uuid
from typing import *
from google.protobuf.message import Message
from google.protobuf.json_format import MessageToDict
from InjusticeJudge.injustice_judge.fetch.majsoul import MahjongSoulAPI, MahjongSoulError, parse_wrapped_bytes, parse_majsoul_link
from InjusticeJudge.injustice_judge.fetch.tenhou import fetch_tenhou
from InjusticeJudge.injustice_judge.fetch.riichicity import RiichiCityAPI
from websockets.exceptions import ConnectionClosedError
import websockets

MS_CHINESE_WSS_ENDPOINT = "wss://gateway-hw.maj-soul.com:443/gateway"
MS_ENGLISH_WSS_ENDPOINT = "wss://mjusgs.mahjongsoul.com:9663/"

class Gateway:
    def __init__(self, ms_api: MahjongSoulAPI,
                       rc_api: RiichiCityAPI) -> None:
        self.logger = logging.getLogger("Gateway")
        self.ms_api = ms_api
        self.rc_api = rc_api
        self.keepalive_task = asyncio.create_task(self.keepalive())

    async def keepalive(self, interval=14400):
        """Calls `heatbeat` for `ms_api` every 4 hours"""
        try:
            while True:
                try:
                    await self.ms_call("heatbeat")
                    self.logger.info(f"keepalive running")
                except MahjongSoulError:
                    # ignore mahjong soul errors not caught in wrapped `call()`
                    pass
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            self.logger.info("`keepalive` task cancelled")
    
    async def relog(self):
        if hasattr(self, "keepalive_task") and self.keepalive_task:
            self.keepalive_task.cancel()
        await self.ms_api.login()
        await self.rc_api.login()
        self.keepalive_task = asyncio.create_task(self.keepalive())

    async def ms_call(self, method, **fields):
        """This is self.ms_api.call() with error handling"""
        try:
            return await self.ms_api.call(method, **fields)
        except MahjongSoulError as e:
            # if you get 1002, you're likely using the wrong endpoint
            if e.code == 1004:
                # relog and retry once more
                self.logger.info("Received `ERR_ACC_NOT_LOGIN`; now trying to log in again and resend the previous request.")
                await self.relog()
                return await self.ms_api.call(method, **fields)
            else:
                raise e
        except ConnectionClosedError:
            # relog and retry once more
            self.logger.info("ConnectionClosed[Error]; now trying to log in again and resend the previous request.")
            await self.relog()
            return await self.ms_api.call(method, **fields)

    async def fetch_majsoul(self, link: str):
        """Uses self.ms_call instead of spinning up a new MahjongSoulAPI"""
        identifier, ms_account_id, player_seat = parse_majsoul_link(link)
        record = await self.ms_call(
            "fetchGameRecord",
            game_uuid=identifier,
            client_version_string=self.ms_api.client_version_string)

        parsed = parse_wrapped_bytes(record.data)[1]
        if parsed.actions != []:  # type: ignore[attr-defined]
            actions = [parse_wrapped_bytes(action.result) for action in parsed.actions if len(action.result) > 0]  # type: ignore[attr-defined]
        else:
            actions = [parse_wrapped_bytes(record) for record in parsed.records]  # type: ignore[attr-defined]

        player = None
        if player_seat is not None:
            player = player_seat
        elif ms_account_id is not None:
            for acc in record.head.accounts:
                if acc.account_id == ms_account_id:
                    player = acc.seat
                    break
        return actions, MessageToDict(record.head), player

    async def fetch_tenhou(self, link: str):
        """Just an async wrapper around fetch_tenhou()"""
        return fetch_tenhou(link)

    async def fetch_riichicity(self, identifier: str):
        """Uses self.rc_api.call() instead of spinning up a new RiichiCityAPI"""
        import json
        player = None
        username = None
        if "@" in identifier:
            identifier, username = identifier.split("@")
            if username in "0123":
                player = int(username)
                username = None
        game_data = await self.rc_api.call("/record/getRoomData", keyValue=identifier)
        if game_data["code"] != 0:
            raise Exception(f"Error {game_data['code']}: {game_data['message']}")
        if username is not None:
            for p in game_data["data"]["handRecord"][0]["players"]:
                if p["nickname"] == username:
                    player_pos = p["position"]
                    starting_dealer_pos = json.loads(game_data["data"]["handRecord"][0]["handEventRecord"][0]["data"])["dealer_pos"]
                    player = (player_pos - starting_dealer_pos) % 4
                    break
        return game_data["data"]["handRecord"], game_data["data"], player
