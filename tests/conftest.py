from pathlib import Path

import pytest

from dst_manager.infrastructure.dst_codec import DstCodec


@pytest.fixture
def tiny_workspace(tmp_path:Path):
    ids=[f"g00000000-0000-0000-0000-{i:012X}" for i in range(1,9)]
    xml=f'''<AcSmDatabase ID="{ids[0]}"><AcSmProp propname="DbVersion">1.1</AcSmProp><AcSmSheetSet ID="{ids[1]}"><AcSmProp propname="Name">测试集</AcSmProp><AcSmSubset ID="{ids[2]}"><AcSmProp propname="Name">分组</AcSmProp><AcSmSheet ID="{ids[3]}"><AcSmCustomPropertyBag ID="{ids[4]}"><AcSmCustomPropertyValue ID="{ids[5]}" propname="比例"><AcSmProp propname="Flags" vt="3">2</AcSmProp><AcSmProp propname="Value" vt="8">1:100</AcSmProp></AcSmCustomPropertyValue></AcSmCustomPropertyBag><AcSmAcDbLayoutReference><AcSmProp propname="AcDbHandle">AB</AcSmProp><AcSmProp propname="FileName">C:\\old\\A.dwg</AcSmProp><AcSmProp propname="Name">001 平面</AcSmProp><AcSmProp propname="Relative_FileName">.\\A.dwg</AcSmProp></AcSmAcDbLayoutReference><AcSmProp propname="Number">001</AcSmProp><AcSmProp propname="Title">平面</AcSmProp><Unknown keep="yes"/></AcSmSheet></AcSmSubset></AcSmSheetSet></AcSmDatabase>'''.encode()
    marker=b'<AcSmProp propname="Name">\xe6\xb5\x8b\xe8\xaf\x95\xe9\x9b\x86</AcSmProp>'
    sheet_set_custom=f'<AcSmCustomPropertyBag ID="{ids[6]}"><AcSmCustomPropertyValue ID="{ids[7]}" propname="项目号"><AcSmProp propname="Flags" vt="3">1</AcSmProp><AcSmProp propname="Value" vt="8">P-000</AcSmProp></AcSmCustomPropertyValue></AcSmCustomPropertyBag>'.encode()
    xml=xml.replace(marker,marker+sheet_set_custom,1)
    (tmp_path/"A.dwg").write_bytes(b"fake"); dst=tmp_path/"test.dst"; DstCodec().encode_file(xml,dst); return dst,ids[3]
