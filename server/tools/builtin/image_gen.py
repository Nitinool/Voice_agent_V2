"""tools/builtin/image_gen.py — 图片生成工具（火山引擎方舟 doubao-seedream）.

调火山方舟 /images/generations 生成图片，下载到本地 frontend/public/generated/，
返回本地 URL（/generated/<id>.jpeg）给前端。vite 自动 serve public/ 目录。

- result_callback 回灌 {url, prompt, local_path} 给 LLM
- 推 RTVIServerMessageFrame{type:'image',url,prompt,id} 给前端（带稳定 id 去重）
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx
from loguru import logger

from pipecat.frames.frames import Frame
from pipecat.processors.frameworks.rtvi.frames import RTVIServerMessageFrame
from pipecat.services.llm_service import FunctionCallParams

from tools.base import ToolDef
from tools.registry import register

_ARK_BASE_URL = os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
_ARK_IMAGE_MODEL = os.environ.get("ARK_IMAGE_MODEL", "doubao-seedream-4-5-251128")

# 图片存到 frontend/public/generated/，vite 自动 serve 为 /generated/<file>
# 路径：server/../frontend/public/generated
_GENERATED_DIR = Path(__file__).resolve().parent.parent.parent.parent / "frontend" / "public" / "generated"
_GENERATED_DIR.mkdir(parents=True, exist_ok=True)


async def _generate_image(params: FunctionCallParams) -> None:
    """根据文字描述生成图片.

    当用户要求画图、生成图片、生成插画时调用此工具。生成后图片会自动发给用户。
    """
    prompt = params.arguments.get("prompt", "").strip()
    if not prompt:
        await params.result_callback({"error": "缺少图片描述 prompt"})
        return

    api_key = os.environ.get("ARK_API_KEY", "")
    if not api_key:
        await params.result_callback({"error": "图片生成服务未配置 ARK_API_KEY"})
        return

    # 1. 调火山 API 生成图片（返回临时 URL）
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_ARK_BASE_URL}/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _ARK_IMAGE_MODEL,
                    "prompt": prompt,
                    "size": "2K",
                    "response_format": "url",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"generate_image 生成请求失败: {e}")
        await params.result_callback({"error": f"图片生成失败: {e}"})
        return

    images = data.get("data", [])
    if not images or not images[0].get("url"):
        await params.result_callback({"error": "图片生成失败：未返回图片"})
        return

    remote_url = images[0]["url"]

    # 2. 下载图片到本地 frontend/public/generated/<id>.jpeg
    img_id = uuid.uuid4().hex[:12]
    local_file = _GENERATED_DIR / f"{img_id}.jpeg"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            img_resp = await client.get(remote_url)
            img_resp.raise_for_status()
            local_file.write_bytes(img_resp.content)
    except (httpx.HTTPError, OSError) as e:
        logger.warning(f"generate_image 下载图片失败: {e}, 用远程 URL 兜底")
        # 兜底：下载失败就用远程 URL（有时效）
        local_url = remote_url
    else:
        # vite serve public/ → /generated/<id>.jpeg
        local_url = f"/generated/{img_id}.jpeg"
        logger.info(f"generate_image 保存: {local_file.name} ({len(img_resp.content)} bytes)")

    # 3. 推 server message 给前端（带稳定 id 去重）
    try:
        await params.pipeline_worker.queue_frames(
            [RTVIServerMessageFrame(
                data={"type": "image", "url": local_url, "prompt": prompt, "id": img_id}
            )]
        )
    except Exception as e:
        logger.warning(f"generate_image 推 frame 给前端失败: {e}")

    # 4. 回灌结果给 LLM（LLM 据此说"图生成好了"）
    await params.result_callback(
        {"url": local_url, "prompt": prompt, "id": img_id, "status": "已生成并发送给用户"}
    )


# 模块导入时自动注册
register(ToolDef(
    name="generate_image",
    description=(
        "根据文字描述生成图片。当用户要求画图、生成图片、生成插画、"
        "『画一只猫』『生成一张风景图』等场景调用此工具。"
        "生成后图片会自动发给用户，你只需简短告诉用户图已生成。"
    ),
    properties={
        "prompt": {
            "type": "string",
            "description": "图片的文字描述，尽量详细，如『一只在草地上奔跑的橘猫，阳光明媚』",
        },
    },
    required=["prompt"],
    handler=_generate_image,
    read_only=False,
))
