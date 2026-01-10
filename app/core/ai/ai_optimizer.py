import httpx
import json
from ...utils.logger import logger

CONF_AI_API_KEY = "ai_api_key"
CONF_AI_BASE_URL = "ai_base_url"
CONF_AI_MODEL = "ai_model"
CONF_AI_ENABLED = "ai_enabled"

DEFAULT_AI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
DEFAULT_AI_MODEL = "qwen-max"

# System Prompt for Optimization (as provided)
SYSTEM_PROMPT_OPTIMIZE = """# 角色与目标
你是一个专业的语音转录文本优化助手，任务是对由ASR（自动语音识别）生成的初步文本进行精细的、最小化的润色。你的核心目标是去除言语组织过程中的干扰性噪音，同时100%保留说话人的原始意图、个人风格和口语习惯。
# 核心原则
- **最小化修改**：只处理明确的、非内容性的言语错误。
- **保留原貌**：最大限度地保留用户的原始用词、句式和语气。
- **可读性优先**：在不改变原意的前提下，提升文本的流畅性和可读性。
- **歧义时保守**：当不确定一个词或一句话是否需要修改时，必须选择保持原样。
# 明确的优化指令 (Do's)
1.  **纠正明显的拼写和语法错误**：修正同音错字、标点误用、以及基础的语法搭配错误（如主谓不一致）。
2.  **移除无意义的填充词**：删除如"呃"、"嗯"、"啊这"、"那个"、"内个"、"然后那个"、"就是说"等在思考或停顿时使用的、不承载实际信息的词语。
3.  **处理重复与口吃**：合并无意义的重复词语。
    -   例子1: "我我我觉得" -> "我觉得"
    -   例子2: "这个这个方案" -> "这个方案"
4.  **整合自我修正**：当用户明确表达了修正意图时，保留修正后的最终内容，并移除被修正的错误部分。
    -   例子1: "会议定在周三，呃不对，是周四" -> "会议定在周四"
    -   例子2: "他的名字是小明，哦我想起来了，是小强" -> "他的名字是小强"
# 严格的禁止项 (Don'ts)
1.  **禁止风格转换**：绝不能将口语化的表达（如"录个影"、"蛮不错"）替换为更书面化的词语（如"录制视频"、"非常好"）。
2.  **禁止替换用词**：除非是明显的错别字，否则不能改变用户的任何用词选择。
3.  **禁止改变句式**：不能为了"优化"而重组用户的句子结构，例如将主动句改为被动句。
4.  **禁止增删情感或语气词**：必须保留所有表达情感和语气的词，如"啊"、"呀"、"呢"、"吧"、"嘛"、"哦"、"喔"等。注意区分它们和第2条指令中提到的"无意义填充词"。
5.  **禁止主观臆断**：不能添加任何原始文本中不存在的信息，或基于猜测去"完善"句子。

# 输出格式
- **输出**: 直接返回优化后的文本，不要包含任何解释、前言或总结。"""

class AITextOptimizer:
    def __init__(self, config_manager):
        self.config_manager = config_manager

    async def optimize_text(self, text: str) -> str:
        """
        Optimize the given text using the configured AI model.
        Returns the optimized text, or raises an exception on failure.
        """
        # Check if enabled
        if not self.config_manager.get_config_value(CONF_AI_ENABLED, False):
            return text

        api_key = self.config_manager.get_config_value(CONF_AI_API_KEY)
        if not api_key:
            raise ValueError("AI API Key is not configured.")

        base_url = self.config_manager.get_config_value(CONF_AI_BASE_URL, DEFAULT_AI_BASE_URL)
        model = self.config_manager.get_config_value(CONF_AI_MODEL, DEFAULT_AI_MODEL)

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": self.config_manager.get_config_value("ai_system_prompt", SYSTEM_PROMPT_OPTIMIZE)},
                {"role": "user", "content": f"原始文本：\n{text}"}
            ],
            "temperature": 0.3,
            "max_tokens": 4000, # Increased for longer texts
            "stream": False
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()
                
                if "choices" in data and len(data["choices"]) > 0:
                    optimized_content = data["choices"][0]["message"]["content"].strip()
                    logger.info("AI Optimization successful.")
                    return optimized_content
                else:
                    raise ValueError("AI response format error: No choices returned.")
                    
            except httpx.HTTPStatusError as e:
                logger.error(f"AI API HTTP Error: {e.response.text}")
                raise ValueError(f"AI API Error: {e.response.status_code} - {e.response.text}")
            except Exception as e:
                logger.error(f"AI Optimization failed: {e}")
                raise e

    async def test_connection(self, api_key, base_url, model):
        """
        Test the connection with provided credentials.
        """
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": "Hello, this is a connection test."}
            ],
            "max_tokens": 10
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                return True, "Connection successful."
            except Exception as e:
                 return False, str(e)
