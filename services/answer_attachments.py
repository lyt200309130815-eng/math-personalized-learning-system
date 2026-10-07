"""Store verified images as files, never SQLite blobs or user-controlled paths."""
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from settings import get_database_path


def save_answer_image(data: bytes, *, database_path=None) -> str:
    if not isinstance(data,bytes) or not data or len(data)>10*1024*1024:
        raise ValueError('解题图片不能为空且不能超过10MB。')
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>20_000_000:
                raise ValueError('仅支持合理尺寸的 PNG/JPEG/WEBP 图片。')
            suffix = {'PNG':'.png','JPEG':'.jpg','WEBP':'.webp'}[image.format]
            image.verify()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as error:
        raise ValueError('无法读取解题图片。') from error
    root = Path(database_path or get_database_path()).resolve().parent/'attachments'
    root.mkdir(parents=True,exist_ok=True)
    path = root/(uuid4().hex+suffix)
    path.write_bytes(data)
    return str(path)
