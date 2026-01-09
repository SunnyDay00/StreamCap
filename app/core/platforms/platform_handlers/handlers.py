import hashlib
import json
import time
import streamget
import httpx

from ....utils.utils import trace_error_decorator
from .base import PlatformHandler, StreamData


class CustomHandler(PlatformHandler):
    platform = "custom"

    def __init__(
            self,
            proxy: str | None = None,
            cookies: str | None = None,
            record_quality: str | None = None,
            platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        stream_data = StreamData(platform="Custom", anchor_name="CustomLive", is_live=True, record_url=live_url)
        if ".flv" in live_url:
            stream_data.flv_url = live_url
        if ".m3u8" in live_url:
            stream_data.flv_url = live_url
        return stream_data


class DouyinHandler(PlatformHandler):
    platform = "douyin"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.DouyinLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        """
        Fetch stream information for a Douyin live URL.
        """
        if not self.live_stream:
            self.live_stream = streamget.DouyinLiveStream(proxy_addr=self.proxy, cookies=self.cookies)

        if "v.douyin.com" in live_url:
            json_data = await self.live_stream.fetch_app_stream_data(url=live_url)
        else:
            json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class TikTokHandler(PlatformHandler):
    platform = "tiktok"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.TikTokLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.TikTokLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class KuaishouHandler(PlatformHandler):
    platform = "kuaishou"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.KwaiLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.KwaiLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class HuyaHandler(PlatformHandler):
    platform = "huya"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.HuyaLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.HuyaLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_app_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class DouyuHandler(PlatformHandler):
    platform = "douyu"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform or self.platform)
        self.live_stream: streamget.DouyuLiveStream | None = None

    async def _fetch_stream_v3(self, rid: str, did: str = '10000000000000000000000000001501') -> dict:
        """
        Fetch stream URL using Douyu V3 API (Reverse engineered from web-encrypt.js).
        """
        enc_url = f"https://www.douyu.com/wgapi/livenc/liveweb/websec/getEncryption?did={did}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"https://www.douyu.com/{rid}"
        }
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Get Encryption Key
            resp = await client.get(enc_url, headers=headers)
            resp.raise_for_status()
            key_resp = resp.json()
            if key_resp.get('error') != 0:
                raise ValueError(f"Douyu Key Error: {key_resp.get('msg')}")
                
            key_data = key_resp['data']
            rand_str = key_data['rand_str']
            enc_time = key_data['enc_time']
            secret_key = key_data['key']
            is_special = key_data['is_special']
            enc_data = key_data.get('enc_data') # Should be top level in data for v3

            # 2. Calculate Signature
            ts = str(int(time.time()))
            payload_str = ""
            if is_special != 1:
                payload_str = str(rid) + ts
                
            u = rand_str
            for _ in range(enc_time):
                u = hashlib.md5((u + secret_key).encode('utf-8')).hexdigest()
                
            auth = hashlib.md5((u + secret_key + payload_str).encode('utf-8')).hexdigest()
            
            # 3. Request Stream URL
            api_url = f"https://www.douyu.com/lapi/live/getH5PlayV1/{rid}"
            body = {
                "enc_data": enc_data,
                "tt": ts,
                "did": did,
                "auth": auth,
                "cdn": "",
                "ver": "Douyu_new",
                "rate": "-1", # Default rate
                "hevc": "0",
                "fa": "0",
                "ive": "0" 
            }
            
            resp2 = await client.post(api_url, headers=headers, data=body)
            resp2.raise_for_status()
            return resp2.json()

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        anchor_name = "Douyu Anchor"
        title = "Douyu Live"
        
        try:
             # 1. Quick check with betard API (no regex needed)
             room_id = live_url.split("/")[-1]
             if "?" in room_id:
                 room_id = room_id.split("?")[0]
             
             api_url = f"https://www.douyu.com/betard/{room_id}"
             headers = {
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                 "Referer": live_url
             }
             
             # Use generic httpx client
             import httpx
             async with httpx.AsyncClient(timeout=5.0) as client:
                 resp = await client.get(api_url, headers=headers)
                 if resp.status_code == 200:
                     data = resp.json()
                     if 'room' in data:
                         room_info = data['room']
                         is_live = room_info.get('show_status') == 1
                         anchor_name = room_info.get('nickname', anchor_name)
                         title = room_info.get('room_name', title)
                         
                         if not is_live:
                             # Return offline immediately without running broken regex
                             return StreamData(
                                 platform=self.platform,
                                 anchor_name=anchor_name,
                                 title=title,
                                 is_live=False,
                                 record_url=live_url
                             )
        except Exception as e:
             # Ignore betard errors and fall through to v3 check
             pass

        # 2. Try V3 API (Custom implementation)
        try:
            # Extract basic room info from StreamData defaults if betard failed
            if anchor_name == "Douyu Anchor" and title == "Douyu Live":
                 pass # Could try to parse page title if absolutely needed, but V3 doesn't give metadata
            
            from ....utils.logger import logger
            
            v3_data = await self._fetch_stream_v3(room_id)
            if v3_data.get('error') == 0:
                data = v3_data['data']
                rtmp_url = data.get('rtmp_url')
                rtmp_live = data.get('rtmp_live')
                
                if rtmp_url and rtmp_live:
                    flv_url = f"{rtmp_url}/{rtmp_live}"
                    # Success!
                    from ....utils.logger import logger
                    logger.info(f"Douyu V3 Fetch Success: {flv_url}")
                    return StreamData(
                        platform=self.platform,
                        anchor_name=anchor_name,
                        title=title,
                        is_live=True,
                        record_url=flv_url
                    )
                else:
                    from ....utils.logger import logger
                    logger.warning(f"Douyu V3 Success but no URL: {v3_data}")
            else:
                from ....utils.logger import logger
                logger.warning(f"Douyu V3 API Failed: {v3_data.get('msg')}")

        except Exception as e:
            from ....utils.logger import logger
            logger.error(f"Douyu V3 Error: {e}")

        # 3. Fallback to streamget (legacy) - Likely to fail but kept as last resort
        try:
            if not self.live_stream:
                self.live_stream = streamget.DouyuLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
            json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
            return await self.live_stream.fetch_stream_url(json_data, self.record_quality)
        except AttributeError as e:
            if "'NoneType' object has no attribute 'group'" in str(e):
                 # Suppress known regex failure
                 from ....utils.logger import logger
                 logger.warning(f"Douyu parser regex mismatch (likely offline or layout changed): {live_url}")
                 return StreamData(
                    platform=self.platform, 
                    is_live=False, 
                    record_url=live_url,
                    anchor_name=anchor_name,
                    title=title
                 )
            raise e
        except Exception as e:
            # Let decorator handle other errors, or swallow?
            raise e


class YYHandler(PlatformHandler):
    platform = "YY"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.YYLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.YYLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class BilibiliHandler(PlatformHandler):
    platform = "bilibili"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.BilibiliLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.BilibiliLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class RedNoteHandler(PlatformHandler):
    platform = "rednote"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.RedNoteLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.RedNoteLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_app_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class BigoHandler(PlatformHandler):
    platform = "bigo"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.BigoLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.BigoLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class BluedHandler(PlatformHandler):
    platform = "blued"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.BluedLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.BluedLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class SoopHandler(PlatformHandler):
    platform = "soop"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform, username, password)
        self.live_stream: streamget.SoopLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.SoopLiveStream(
                proxy_addr=self.proxy, cookies=self.cookies, username=self.username, password=self.password
            )
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class NeteaseHandler(PlatformHandler):
    platform = "netease"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.NeteaseLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.NeteaseLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class QiandureboHandler(PlatformHandler):
    platform = "qiandurebo"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.QiandureboLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.QiandureboLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class PamdaTVHandler(PlatformHandler):
    platform = "pandatv"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.PandaLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.PandaLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class MaoerFMHandler(PlatformHandler):
    platform = "maoerfm"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.MaoerLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.MaoerLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class LookHandler(PlatformHandler):
    platform = "look"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.LookLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.LookLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class WinkTVHandler(PlatformHandler):
    platform = "winktv"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.WinkTVLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.WinkTVLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class FlexTVHandler(PlatformHandler):
    platform = "flextv"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform, username, password)
        self.live_stream: streamget.FlexTVLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.FlexTVLiveStream(
                proxy_addr=self.proxy, cookies=self.cookies, username=self.username, password=self.password
            )
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class PopkonTVHandler(PlatformHandler):
    platform = "popkontv"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform, username, password)
        self.live_stream: streamget.PopkonTVLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.PopkonTVLiveStream(
                proxy_addr=self.proxy, cookies=self.cookies, username=self.username, password=self.password
            )
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class TwitcastingHandler(PlatformHandler):
    platform = "twitcasting"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform, username, password)
        self.live_stream: streamget.TwitCastingLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.TwitCastingLiveStream(
                proxy_addr=self.proxy, cookies=self.cookies, username=self.username, password=self.password
            )
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class BaiduHandler(PlatformHandler):
    platform = "baidu"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.BaiduLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.BaiduLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class WeiboHandler(PlatformHandler):
    platform = "weibo"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.WeiboLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.WeiboLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class KugouHandler(PlatformHandler):
    platform = "kugou"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.KugouLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.KugouLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class TwitchHandler(PlatformHandler):
    platform = "twitch"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.TwitchLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.TwitchLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class LivemeHandler(PlatformHandler):
    platform = "liveme"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.LiveMeLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.LiveMeLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class HuajiaoHandler(PlatformHandler):
    platform = "huajiao"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.HuajiaoLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.HuajiaoLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class ShowRoomHandlerHandler(PlatformHandler):
    platform = "showroom"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.ShowRoomLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.ShowRoomLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class AcfunHandler(PlatformHandler):
    platform = "acfun"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.AcfunLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.AcfunLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class InkeHandler(PlatformHandler):
    platform = "inke"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.InkeLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.InkeLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class YinboHandler(PlatformHandler):
    platform = "yinbo"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.YinboLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.YinboLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class ChangliaoHandler(PlatformHandler):
    platform = "changliao"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.ChangliaoLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.ChangliaoLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class ZhihuHandler(PlatformHandler):
    platform = "zhihu"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.ZhihuLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.ZhihuLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class ChzzkHandler(PlatformHandler):
    platform = "chzzk"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.ChzzkLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.ChzzkLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class HaixiuHandler(PlatformHandler):
    platform = "haixiu"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.HaixiuLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.HaixiuLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class VVXQHandler(PlatformHandler):
    platform = "vvxqiu"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.VVXQLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.VVXQLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class YiqiLiveHandler(PlatformHandler):
    platform = "17live"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.YiqiLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.YiqiLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class LangLiveHandler(PlatformHandler):
    platform = "langlive"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.LangLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.LangLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class PiaopiaoHandler(PlatformHandler):
    platform = "piaopiao"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.PiaopaioLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.PiaopaioLiveStream(proxy_addr=self.proxy, cookies=self.cookies)

        if 'preview.html' not in live_url:
            json_data = await self.live_stream.fetch_app_stream_data(url=live_url)
        else:
            json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class SixRoomHandler(PlatformHandler):
    platform = "sixroom"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.SixRoomLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.SixRoomLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class LehaiHandler(PlatformHandler):
    platform = "lehai"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.LehaiLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.LehaiLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class HuamaoHandler(PlatformHandler):
    platform = "huamao"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.HuamaoLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.HuamaoLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class ShopeeHandler(PlatformHandler):
    platform = "shopee"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.ShopeeLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.ShopeeLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class YoutubeHandler(PlatformHandler):
    platform = "youtube"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.YoutubeLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.YoutubeLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class TaobaoHandler(PlatformHandler):
    platform = "taobao"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.TaobaoLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.TaobaoLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class JDHandler(PlatformHandler):
    platform = "jd"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.JDLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.JDLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class FaceitHandler(PlatformHandler):
    platform = "faceit"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.FaceitLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.FaceitLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class LianJieHandler(PlatformHandler):
    platform = "lianjie"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.LianJieLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.LianJieLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class MiguHandler(PlatformHandler):
    platform = "migu"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.MiguLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.MiguLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class LaixiuHandler(PlatformHandler):
    platform = "laixiu"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.LaixiuLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.LaixiuLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


class PicartoHandler(PlatformHandler):
    platform = "picarto"

    def __init__(
        self,
        proxy: str | None = None,
        cookies: str | None = None,
        record_quality: str | None = None,
        platform: str | None = None,
    ) -> None:
        super().__init__(proxy, cookies, record_quality, platform)
        self.live_stream: streamget.PicartoLiveStream | None = None

    @trace_error_decorator
    async def get_stream_info(self, live_url: str) -> StreamData:
        if not self.live_stream:
            self.live_stream = streamget.PicartoLiveStream(proxy_addr=self.proxy, cookies=self.cookies)
        json_data = await self.live_stream.fetch_web_stream_data(url=live_url)
        return await self.live_stream.fetch_stream_url(json_data, self.record_quality)


CustomHandler.register(r"https?://.*\.(?:flv|m3u8)(\?.*)?$")
DouyinHandler.register(r"https://.*\.douyin\.com/")
TikTokHandler.register(r"https://.*\.tiktok\.com/")
KuaishouHandler.register(r"https://live\.kuaishou\.com/")
HuyaHandler.register(r"https://.*\.huya\.com/")
DouyuHandler.register(r"https://.*\.douyu\.com/")
YYHandler.register(r"https://.*\.yy\.com/")
BilibiliHandler.register(r"https://live\.bilibili\.com/")
RedNoteHandler.register(r"www\.xiaohongshu\.com/", r"xhslink\.com/")
BigoHandler.register(r"https://www\.bigo\.tv/", r"https://slink\.bigovideo\.tv/")
BluedHandler.register(r"https://app\.blued\.cn/")
SoopHandler.register(r"sooplive\.co\.kr/")
SoopHandler.register(r"sooplive\.com/")
NeteaseHandler.register(r"cc\.163\.com/")
QiandureboHandler.register(r"qiandurebo.com/")
PamdaTVHandler.register(r".*\.pandalive.co.kr/")
MaoerFMHandler.register(r"fm.missevan.com/")
LookHandler.register(r"look.163.com/")
WinkTVHandler.register(r"www.winktv.co.kr/")
FlexTVHandler.register(r"www\.flextv\.co\.kr/", r"www\.ttinglive\.com/")
PopkonTVHandler.register(r"www\.popkontv\.com/")
TwitcastingHandler.register(r"twitcasting\.tv")
BaiduHandler.register(r".*\.baidu\.com")
WeiboHandler.register(r"weibo\.com/")
KugouHandler.register(r".*\.kugou\.com")
TwitchHandler.register(r"https://.*\.twitch\.tv/")
LivemeHandler.register(r"https://.*\.liveme\.com/")
HuajiaoHandler.register(r"https://.*\.huajiao\.com/")
ShowRoomHandlerHandler.register(r".*\.showroom-live\.com")
AcfunHandler.register(r"live.acfun.cn/")
InkeHandler.register(r"https://.*\.inke\.cn/")
YinboHandler.register(r"live.ybw1666.com")
ChangliaoHandler.register(r".*\.tlclw\.com")
ZhihuHandler.register(r"https://.*\.zhihu\.com/")
ChzzkHandler.register(r"chzzk\.naver\.com/")
HaixiuHandler.register(r"https://.*\.haixiutv\.com/")
VVXQHandler.register(r".*\.vvxqiu\.com")
YiqiLiveHandler.register(r"17\.live")
LangLiveHandler.register(r"https://.*\.lang\.live/")
PiaopiaoHandler.register(r".*\.weimipopo.com/")
SixRoomHandler.register(r"v.6.cn/")
LehaiHandler.register(r"https://.*\.lehaitv\.com/")
HuamaoHandler.register(r"h.catshow168.com")
ShopeeHandler.register(r".*.shp.ee/")
YoutubeHandler.register(r".*\.youtube\.com/")
TaobaoHandler.register(r".*\.tb\.cn/", r"https://.*\.taobao\.com/")
JDHandler.register(r"3\.cn/")
FaceitHandler.register(r"https://.*\.faceit\.com/")
LianJieHandler.register(r"https://.*\.lailianjie\.com/")
MiguHandler.register(r"https://.*\.miguvideo\.com/")
LaixiuHandler.register(r"https://.*\.imkktv\.com/")
PicartoHandler.register(r"https://.*\.picarto\.tv/")
