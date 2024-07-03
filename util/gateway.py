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
from InjusticeJudge.injustice_judge.fetch.majsoul import MahjongSoulAPI, parse_wrapped_bytes, parse_majsoul_link
from websockets.exceptions import ConnectionClosedError

class GeneralMajsoulError(Exception):
    def __init__(self, errorCode: int, message: str):
        self.errorCode = errorCode
        self.message = f"ERROR CODE {errorCode}: {message}"
        super().__init__(self.message)

class Gateway(MahjongSoulAPI):
    """Helper class to interface with the Mahjong Soul API"""
    def __init__(self, endpoint: str, mjs_username: Optional[str]=None, mjs_password: Optional[str]=None, mjs_uid: Optional[str]=None, mjs_token: Optional[str]=None) -> None:
        super().__init__(endpoint)
        self.logger = logging.getLogger("Gateway")
        self.mjs_username = mjs_username
        self.mjs_password = mjs_password
        self.mjs_uid = mjs_uid
        self.mjs_token = mjs_token
        self.use_cn = self.mjs_username is not None and self.mjs_password is not None
        self.use_en = self.mjs_uid is not None and self.mjs_token is not None
        if not self.use_cn and not self.use_en:
            raise Exception("Gateway was initialized without login credentials!")

    async def login_en(self):
        UID = self.mjs_uid
        TOKEN = self.mjs_token
        MS_VERSION = requests.get(url="https://mahjongsoul.game.yo-star.com/version.json").json()["version"][:-2]
        self.logger.info(f"Fetched Mahjong Soul version: {MS_VERSION}")
        self.client_version_string = f"web-{MS_VERSION[:-2]}"
        self.logger.info("Calling heatbeat...")
        await self.call("heatbeat")
        self.logger.info("Requesting initial access token...")
        USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/110.0"
        access_token = requests.post(url="https://passport.mahjongsoul.com/user/login", headers={"User-Agent": USER_AGENT, "Referer": "https://mahjongsoul.game.yo-star.com/"}, data={"uid":UID,"token":TOKEN,"deviceId":f"web|{UID}"}).json()["accessToken"]
        self.logger.info("Requesting oauth access token...")
        oauth_token = (await self.call("oauth2Auth", type=7, code=access_token, uid=UID, client_version_string=f"web-{MS_VERSION}")).access_token
        self.logger.info("Calling heatbeat...")
        await self.call("heatbeat")
        self.logger.info("Calling oauth2Check...")
        assert (await self.call("oauth2Check", type=7, access_token=oauth_token)).has_account, "couldn't find account with oauth2Check"
        self.logger.info("Calling oauth2Login...")
        client_device_info = {"platform": "pc", "hardware": "pc", "os": "mac", "is_browser": True, "software": "Firefox", "sale_platform": "web"}
        await self.call("oauth2Login", type=7, access_token=oauth_token, reconnect=False, device=client_device_info, random_key=str(uuid.uuid1()), client_version={"resource": f"{MS_VERSION}.w"}, currency_platforms=[], client_version_string=f"web-{MS_VERSION}", tag="en")
        self.logger.info(f"`login` with token successful!")

    async def login_cn(self):
        """
        this is its own method so it can be used again without having to establish
        another WSS connection (e.g., when we were logged out outside of this module)
        NOTE: this method starts the `huge_ping` task. It should be canceled before
        reusing this method.
        NOTE: use `super().call()` to avoid infinite errors
        """
        # following sequence is inspired by `mahjong_soul_api`:
        # https://github.com/MahjongRepository/mahjong_soul_api/blob/master/example.py
        # ms_version example: 0.10.269.w
        ms_version = requests.get(url="https://game.maj-soul.com/1/version.json").json()["version"]
        self.logger.info(f"Fetched Mahjong Soul version: {ms_version}")

        self.client_version_string = f"web-{ms_version[:-2]}"
        client_device_info = {"is_browser": True}
        await self.call(
            "login",
            account=self.mjs_username,
            password=hmac.new(b"lailai", self.mjs_password.encode(), hashlib.sha256).hexdigest(),
            device=client_device_info,
            random_key=str(uuid.uuid1()),
            client_version_string=self.client_version_string)
        
        self.logger.info(f"`login` with {self.mjs_username} successful!")
    
    async def login(self):
        """
        this is its own method so it can be used again without having to establish
        another WSS connection (e.g., when we were logged out outside of this module)
        NOTE: this method starts the `huge_ping` task. It should be canceled before
        reusing this method.
        NOTE: use `self.call()` to avoid infinite errors
        """
        if self.use_cn:
            await self.login_cn()
        elif self.use_en:
            await self.login_en()

        self.huge_ping_task = asyncio.create_task(self.huge_ping())
    
    async def huge_ping(self, huge_ping_interval=14400):
        """
        this task tries to call `heatbeat` every 4 hours so we know when
        we need to attempt reconnection (via the wrapped `call()`)
        """
        try:
            while True:
                try:
                    await self.call("heatbeat")
                    self.logger.info(f"huge_ping'd.")
                except GeneralMajsoulError:
                    # ignore mahjong soul errors not caught in wrapped `call()`
                    pass
                await asyncio.sleep(huge_ping_interval)
        except asyncio.CancelledError:
            self.logger.info("`huge_ping` task cancelled")

    async def connect_and_login(self):
        """
        Connect to the Chinese game server and login with username and password.
        """
        try:
            if self.use_cn:
                await self.connect(MS_CHINESE_WSS_ENDPOINT)
            else:
                await self.connect(MS_ENGLISH_WSS_ENDPOINT)
            await self.login()
        except InvalidStatusCode as e:
            self.logger.error("Failed to login for Lobby. Is Mahjong Soul currently undergoing maintenance?")
            raise e
    
    async def reconnect_and_login(self):
        """
        login to Mahjong Soul again, keeping the existing subscriptions.
        Needs to make a new connection with `self.reconnect()` because trying to
        log in through the same connection results in `2504 : "ERR_CONTEST_MGR_HAS_LOGINED"`
        """
        if hasattr(self, "huge_ping_task") and self.huge_ping_task:
            self.huge_ping_task.cancel()
        await self.login()

    async def call(self, methodName, **msgFields):
        """
        Wrap around `MajsoulChannel.call()` to handle certain errors. Note that
        `MajsoulChannel` already prints the API Errors to the console.
        """
        try:
            return await super().call(methodName, **msgFields)
        except GeneralMajsoulError as mjsError:
            if mjsError.errorCode == 1004:
                """
                "ERR_ACC_NOT_LOGIN"
                In this case, try logging BACK in and retrying the call.
                Do nothing if the retry still failed. (we do this because
                the account may have been logged out elsewhere unintentionally)
                """
                self.logger.info("Received `ERR_ACC_NOT_LOGIN`; now trying to log in again and resend the previous request.")
                await self.reconnect_and_login()
                return await super().call(methodName, **msgFields)
            else:
                # raise other GeneralMajsoulError
                raise mjsError
        except ConnectionClosedError:
            """
            similar to above; try logging back in once and retrying the call.
            Do nothing if the retry still failed.
            """
            self.logger.info("ConnectionClosed[Error]; now trying to log in again and resend the previous request.")
            await self.reconnect_and_login()
            return await super().call(methodName, **msgFields)

    async def fetch_majsoul(self, link: str):
        """
        NOTE:
        basically the same as InjusticeJudge's `fetch_majsoul()`, with 1 difference;
        Instead of logging in for each fetch, just fetch through the already logged-in
        AccountManager.
        """
        identifier_pattern = r'\?paipu=([0-9a-zA-Z-]+)'
        identifier_match = re.search(identifier_pattern, link)
        if identifier_match is None:
            raise Exception(f"Invalid Mahjong Soul link: {link}")
        identifier = identifier_match.group(1)

        if not all(c in "0123456789abcdef-" for c in identifier):
            # deanonymize the link
            codex = "0123456789abcdefghijklmnopqrstuvwxyz"
            decoded = ""
            for i, c in enumerate(identifier):
                decoded += "-" if c == "-" else codex[(codex.index(c) - i + 55) % 36]
            identifier = decoded
        
        record = await self.call(
            "fetchGameRecord",
            game_uuid=identifier,
            client_version_string=self.client_version_string)

        parsed = parse_wrapped_bytes(record.data)[1]
        if parsed.actions != []:  # type: ignore[attr-defined]
            actions = [parse_wrapped_bytes(action.result) for action in parsed.actions if len(action.result) > 0]  # type: ignore[attr-defined]
        else:
            actions = [parse_wrapped_bytes(record) for record in parsed.records]  # type: ignore[attr-defined]
        
        player = 0
        if link.count("_") == 2:
            player = int(link[-1])
        else:
            player_pattern = r'_a(\d+)'
            player_match = re.search(player_pattern, link)
            if player_match is not None:
                ms_account_id = int((((int(player_match.group(1))-1358437)^86216345)-1117113)/7)
                for acc in record.head.accounts:
                    if acc.account_id == ms_account_id:
                        player = acc.seat
                        break
        
        return actions, MessageToDict(record.head), player
