import hashlib
from pathlib import Path

from lxml import etree


class CodecError(ValueError):
    pass


_DECODE = bytes.fromhex(
    "8c8b8e8d88878a8984838685807f8281 7c7b7e7d78777a7974737675706f7271 "
    "acabaeada8a7aaa9a4a3a6a5a09fa2a1 9c9b9e9d98979a9994939695908f9291 "
    "cccbcecdc8c7cac9c4c3c6c5c0bfc2c1 bcbbbebdb8b7bab9b4b3b6b5b0afb2b1 "
    "ecebe eede8e7eae9e4e3e6e5e0dfe2e1 dcd bdeddd8d7dad9d4d3d6d5d0cfd2d1".replace(" ", "")
    + "0c0b0e0d08070a090403060500ff0201fcfbfefdf8f7faf9f4f3f6f5f0eff2f1"
    + "2c2b2e2d28272a2924232625201f22211c1b1e1d18171a1914131615100f1211"
    + "4c4b4e4d48474a4944434645403f42413c3b3e3d38373a3934333635302f3231"
    + "6c6b6e6d68676a6964636665605f62615c5b5e5d58575a5954535655504f5251"
)

# 上面的常量需要严格保持为256项；导入时即失败可避免静默损坏DST。
if len(_DECODE) != 256:
    raise RuntimeError(f"DST解码表长度错误：{len(_DECODE)}")

_encode = bytearray(256)
for encoded_byte, plain_byte in enumerate(_DECODE):
    _encode[plain_byte] = encoded_byte
_ENCODE = bytes(_encode)


class DstCodec:
    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def decode_bytes(self, data: bytes) -> bytes:
        xml = data.translate(_DECODE)
        try:
            etree.fromstring(xml)
        except (etree.XMLSyntaxError, ValueError) as exc:
            raise CodecError(f"DST_DECODE_INVALID_XML: {exc}") from exc
        return xml

    def encode_bytes(self, xml: bytes) -> bytes:
        try:
            etree.fromstring(xml)
        except (etree.XMLSyntaxError, ValueError) as exc:
            raise CodecError(f"XML_INVALID: {exc}") from exc
        return xml.translate(_ENCODE)

    def decode_file(self, source: Path) -> bytes:
        if not source.is_file():
            raise CodecError(f"DST_NOT_FOUND: {source}")
        return self.decode_bytes(source.read_bytes())

    def encode_file(self, xml: bytes, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.encode_bytes(xml))
