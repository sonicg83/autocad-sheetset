---
id: RES-SH-003
title: Transform 插件矩阵运算准确性分析
status: accepted
owners: [shared]
created: 2026-07-15
updated: 2026-08-17
---

# Transform 插件矩阵运算准确性分析

## 1. 文档目的

本文结合 Autodesk 官方的 `Matrix3d`、WCS/UCS 和 AutoCAD Map 3D 坐标转换说明，分析 `Transform` 插件中 `CoT`、`UCoT` 两条命令的矩阵构造是否准确合理，并明确以下问题：

- `PreMultiplyBy` 的矩阵顺序是否正确；
- 正向转换是否符合二维四参数相似变换；
- 恢复矩阵是否为严格逆矩阵；
- 当前默认参数的实际往返误差；
- WCS/UCS、旋转方向和坐标轴约定；
- Z 坐标、三维实体和标注对象受到的影响；
- 当前算法与完整地理坐标系转换之间的边界；
- 后续重构和验收应建立的测试标准。

分析对象主要包括：

- 历史本地路径 `plugin/Transform/Transform/myCommands.cs`；
- 历史本地路径 `plugin/Transform/Transform/myPlugin.cs`；
- 历史本地路径 `plugin/Transform/Transform/bin/Debug/config.ini`；
- 历史本地路径 `plugin/Transform/Transform/obj/Debug/config.ini`；
- 历史本地路径 `plugin/Transform/change.txt`。

本文只分析源码和已有配置。仓库没有控制点成果表、源/目标坐标系定义、参数解算报告或黄金 DWG，因此无法仅凭源码证明参数具有测绘精度。

## 2. 结论摘要

`Transform` 插件的核心矩阵乘法在代数上是正确的：

```text
正向：P' = B + s·R(θ)·P
恢复：P  = (1/s)·R(-θ)·(P' - B)
```

它等价于标准二维四参数相似变换，其中：

- `B=(DX,DY)` 是平移项；
- `θ` 是绕 WCS 正 Z 轴的旋转角；
- `s` 是统一比例因子。

当正向和恢复使用同一组 `B、θ、s` 时，`RecoverEntity` 是 `TransformEntity` 的严格代数逆变换。使用双精度计算，典型测试点的往返误差约为 `10^-10` 个图形单位。

但当前插件整体不能直接判定为准确可靠：

1. 随 DLL 保存的 `bin/Debug/config.ini` 与源码读取格式不兼容，实际会落回硬编码参数；
2. `CoT` 和 `UCoT` 的硬编码默认参数不同，默认往返不是严格可逆；
3. `Matrix3d.Scaling` 是三维统一缩放，会改变非零 Z 坐标；
4. 插件没有读取或转换当前 UCS，全部参数实际上按 WCS 解释；
5. 算法只是移动、旋转和缩放实体，不等于完整的投影或大地坐标系转换；
6. 单个实体失败后仍提交事务，可能产生部分实体已转换、部分实体未转换的混合状态；
7. 没有参数来源、控制点残差、有效范围和验收阈值，无法判断参数本身是否正确。

因此应当区分：

```text
矩阵公式：基本准确
默认运行状态：不严格可逆
二维局部相似变换：适用
三维高程或完整 CRS 转换：不充分
参数物理精度：证据不足
```

## 3. Autodesk 官方矩阵约定

### 3.1 Matrix3d 使用列向量

Autodesk 将 `Matrix3d` 定义为三维空间中的 4×4 仿射变换矩阵：

```text
| a00 a01 a02 t0 |
| a10 a11 a12 t1 |
| a20 a21 a22 t2 |
|  0   0   0   1 |
```

点使用齐次列向量表示，变换方式为：

```text
P' = M × P
```

因此在组合矩阵 `M=A×B×C` 中，右侧的 `C` 最先作用于点。

官方依据：

- [Matrix3d Structure](https://help.autodesk.com/cloudhelp/2024/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_Geometry_Matrix3d.html)
- [Transform Objects (.NET)](https://help.autodesk.com/view/ACDLT/2026/ENU/?caas=caas%2Fdocumentation%2FACD%2F2014%2FENU%2Ffiles%2FGUID-D4348E23-7ECB-48F6-90B7-FB7EF42DFA8D-htm.html)

### 3.2 PreMultiplyBy 和 PostMultiplyBy

Autodesk 对乘法方法的定义是：

```text
matrix.PreMultiplyBy(left)   = left × matrix
matrix.PostMultiplyBy(right) = matrix × right
```

官方依据：

- [Matrix3d Methods](https://help.autodesk.com/view/OARX/2025/ENU/?guid=OARX-ManagedRefGuide-__MEMBERTYPE_Methods_Autodesk_AutoCAD_Geometry_Matrix3d)

理解这一点是判断当前源码是否正确的关键。如果误把 `PreMultiplyBy` 理解为“把新矩阵追加到右侧”，就会得出相反结论。

### 3.3 Rotation 和 Scaling

`Matrix3d.Rotation` 使用：

- 弧度角；
- 旋转轴 `Vector3d`；
- 旋转轴经过的基点 `Point3d`。

`Matrix3d.Scaling(double, Point3d)` 表示以指定点为中心的三维统一比例缩放。

官方依据：

- [Rotate Objects (.NET)](https://help.autodesk.com/cloudhelp/2024/CHS/OARX-DevGuide-Managed/files/GUID-DAF76951-DD0C-413F-86A8-471E2B94C1C0.htm)
- [Matrix3d.Scaling Method](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_Geometry_Matrix3d_Scaling_double_Point3d.html)

## 4. 正向矩阵推导

### 4.1 源码

`TransformEntity` 的核心代码为：

```csharp
Point3d origon = new Point3d(0, 0, 0);
Vector3d zaxis = new Vector3d(0, 0, 1);

Matrix3d smat = Matrix3d.Scaling(scale, basepoint);
Matrix3d rmat = Matrix3d.Rotation(rangle, zaxis, basepoint);
Matrix3d dmat = Matrix3d.Displacement(origon.GetVectorTo(basepoint));

Matrix3d mat = dmat.PreMultiplyBy(rmat).PreMultiplyBy(smat);
entity.TransformBy(mat);
```

设：

```text
B = (dx, dy, 0)
s = 比例因子
θ = 旋转角
T_B = 平移 +B
R_B = 绕 B 旋转 θ
S_B = 以 B 为中心缩放 s
```

根据 `PreMultiplyBy` 的官方定义：

```text
dmat.PreMultiplyBy(rmat)
= R_B × T_B

继续 PreMultiplyBy(smat)
= S_B × R_B × T_B
```

所以正向矩阵为：

```text
M正 = S_B × R_B × T_B
```

对点的实际执行顺序是：

1. 把点平移 `+B`；
2. 绕 `B` 旋转；
3. 以 `B` 为中心缩放。

### 4.2 矩阵化简

绕点和以点为中心缩放可以写为：

```text
R_B = T_B × R × T_-B
S_B = T_B × S × T_-B
```

代入正向矩阵：

```text
M正
= S_B × R_B × T_B
= (T_B × S × T_-B)
  × (T_B × R × T_-B)
  × T_B
= T_B × S × R
```

统一比例缩放和同一平面旋转可交换，所以也可以写为：

```text
M正 = T_B × R × S
```

最终二维点公式为：

```text
P' = B + s·R(θ)·P
```

展开后：

```text
X' = dx + s·cosθ·X - s·sinθ·Y
Y' = dy + s·sinθ·X + s·cosθ·Y
```

这就是标准二维四参数相似变换。

### 4.3 与 Autodesk ADETRANSFORM 的对应关系

AutoCAD Map 3D 的 `ADETRANSFORM` 使用两组源点和目标点决定：

- 第一组点的差值决定偏移；
- 两组线段的角度差决定旋转；
- 目标线段长度与源线段长度的比值决定比例。

当前插件的数学模型与这种二维移动、旋转和统一缩放模型一致。

官方依据：

- [ADETRANSFORM (Transform Command)](https://help.autodesk.com/cloudhelp/2023/ENU/MAP3D-Use/files/GUID-AB726381-7DD2-49D0-9902-C1300C636A7C.htm)

## 5. 当前正向默认参数

`CoT` 的硬编码默认值为：

```text
dx = 391090.578160
dy = 2472660.598025
θ  = 0.0170603779 rad
s  = 0.999997425176
```

换算后：

```text
θ ≈ 0.977487651°
尺度改正 ≈ -2.574824 ppm
```

二维矩阵系数为：

```text
a = s·cosθ = 0.999851900833366
b = s·sinθ = 0.017059506397741
```

实际坐标公式为：

```text
X' = 391090.578160
     + 0.999851900833366·X
     - 0.017059506397741·Y

Y' = 2472660.598025
     + 0.017059506397741·X
     + 0.999851900833366·Y
```

在 AutoCAD 的列向量和正 Z 轴旋转约定下，这个公式是准确的。

## 6. basepoint 参数的真实含义

变量名 `basepoint` 容易让维护者把它理解为“旋转和缩放过程中保持不动的基点”。但经过化简后：

```text
P' = B + sRP
```

因此 `B` 的真实含义是：

```text
源坐标系原点 (0,0) 在目标坐标系中的坐标
```

也就是最终仿射矩阵的平移项。这与命令输出中的“偏移后原点”基本一致。

如果四参数由一对非原点控制点 `P1→Q1` 求得，则应满足：

```text
B = Q1 - sR·P1
```

只有当源控制点 `P1=(0,0)` 时，`B` 才等于目标控制点 `Q1`。

因此配置文档应明确：

```text
DX/DY 是仿射平移项，不是任意旋转基点，也不一定等于第一个目标控制点。
```

## 7. 恢复矩阵推导

### 7.1 源码

`RecoverEntity` 的核心代码为：

```csharp
double newscale = 1 / scale;

Matrix3d smat = Matrix3d.Scaling(newscale, basepoint);
Matrix3d rmat = Matrix3d.Rotation(-rangle, zaxis, basepoint);
Matrix3d dmat = Matrix3d.Displacement(basepoint.GetVectorTo(origion));

Matrix3d mat = smat.PreMultiplyBy(rmat).PreMultiplyBy(dmat);
entity.TransformBy(mat);
```

根据 `PreMultiplyBy` 规则：

```text
M恢 = T_-B × R_B(-θ) × S_B(1/s)
```

化简后：

```text
M恢 = R(-θ) × S(1/s) × T_-B
```

作用于目标点：

```text
P = (1/s)·R(-θ)·(P' - B)
```

展开为：

```text
X = [ cosθ·(X'-dx) + sinθ·(Y'-dy) ] / s
Y = [-sinθ·(X'-dx) + cosθ·(Y'-dy) ] / s
```

### 7.2 可逆性结论

当恢复使用与正向完全相同的 `B、θ、s` 时：

```text
M恢 = M正^-1
```

对以下点使用当前正向参数进行公式级双精度往返验证：

```text
(0, 0)
(1000, 2000)
(100000, 200000)
```

所得误差约为 `0～9×10^-11` 个图形单位，属于浮点舍入范围。

所以 `RecoverEntity` 的矩阵顺序本身没有问题。

## 8. 当前默认运行状态并不严格可逆

### 8.1 配置文件格式不兼容

源码读取以下配置：

```ini
[Displacement]
X=391090.57816
Y=2472660.598025

[Rotation]
radian=0.0170603779

[Scale]
scale=0.999997425176
```

但 `bin/Debug/config.ini` 使用：

```ini
[默认参数]
DX=391090.57816
DY=2472660.598025
R=0.0170603779
S=0.999997425176
```

源码无法从该文件读取 `Displacement/X`，`Convert.ToDouble("")` 会失败。异常被捕获后，命令继续使用硬编码默认值。

此外，配置解析不是原子操作：

1. 先解析 X；
2. 再解析 Y；
3. 立即更新 `basepoint`；
4. 再解析旋转；
5. 最后解析比例。

如果旋转或比例阶段失败，命令可能混用新平移值和旧旋转/比例值。

### 8.2 CoT 和 UCoT 默认参数不同

`CoT` 默认参数：

```text
B正 = (391090.578160, 2472660.598025)
θ正 = 0.0170603779
s正 = 0.999997425176
```

`UCoT` 默认参数：

```text
B恢 = (391090.522451, 2472660.716344)
θ恢 = 0.0170593097
s恢 = 0.999997530712
```

差异为：

```text
ΔB = (0.055709, -0.118319)
Δθ = 0.0000010682 rad ≈ 0.220332″
s正/s恢 - 1 ≈ -0.105536 ppm
```

如果先执行默认 `CoT`，再执行默认 `UCoT`，组合结果为：

```text
P'' = (s正/s恢)·R(θ正-θ恢)·P
      + (1/s恢)·R(-θ恢)·(B正-B恢)
```

对于源原点 `(0,0)`，残余误差约为：

```text
ΔX ≈ +0.053683
ΔY ≈ -0.119252
平面误差 ≈ 0.130778 个图形单位
```

如果图形单位是米，相当于约 13.1 cm。

两组参数的线性部分相差约 `1.073 ppm`，相当于每 1 km 坐标基线约产生额外 1.07 mm 差异。最终误差还会与残余平移叠加或抵消，不能简单按距离单独估算。

因此：

```text
有效且同一组配置：CoT/UCoT 严格可逆
当前无效发布配置：CoT/UCoT 使用不同默认值，不严格可逆
```

两组默认值可能是正反方向分别拟合的参数，但仓库没有控制点、参数解算过程或残差报告，不能确认这种设计是否有意且能提高实际精度。

## 9. 旋转方向和轴序

代码使用：

```csharp
Vector3d zaxis = new Vector3d(0, 0, 1);
Matrix3d.Rotation(rangle, zaxis, basepoint);
```

这表示固定绕 WCS 正 Z 轴旋转。在 AutoCAD 右手坐标系下：

```text
正角：从正 Z 方向看，XY 平面逆时针旋转
负角：顺时针旋转
```

当前公式：

```text
X' = aX - bY
Y' = bX + aY
```

与这一约定一致。

但测量坐标经常采用：

- X 表示北坐标；
- Y 表示东坐标；
- 方位角从北方向起算；
- 顺时针为正。

如果四参数使用这种测量约定求得，就必须先换算为 AutoCAD 笛卡尔 XY 和逆时针正角约定。当前配置没有记录：

- X/Y 分别表示什么；
- 是否交换轴；
- 角度是顺时针还是逆时针；
- 角度从 X 轴还是北方向起算。

因此可以确认 AutoCAD 矩阵方向正确，但不能确认现有测绘参数方向正确。

## 10. WCS 和 UCS 边界

插件加载时提示用户“请注意要在世界坐标系下使用命令”，但代码：

- 不读取 `Editor.CurrentUserCoordinateSystem`；
- 不判断当前 UCS 是否为 WCS；
- 不调用 `Matrix3d.AlignCoordinateSystem`；
- 固定使用 `(0,0,1)` 作为旋转轴；
- 不要求用户在当前 UCS 中拾取控制点。

Autodesk 官方在需要进行 UCS/WCS 转换时，会读取当前 UCS 矩阵，并使用 `AlignCoordinateSystem` 或等效方式转换点和轴。

官方依据：

- [Define a User Coordinate System (.NET)](https://help.autodesk.com/cloudhelp/2017/ITA/AutoCAD-NET/files/GUID-096085E3-5AD5-4454-BF10-C9177FDB5979.htm)

当前实现的真实参数契约是：

```text
DX、DY、旋转轴和角度全部按 WCS 解释。
```

由于命令没有用户坐标输入，当前 UCS 通常不会改变固定 WCS 矩阵作用于数据库实体的结果。因此“必须切换到 WCS”更像操作提示，不是代码上的强制条件。

后续实现应明确选择：

1. 固定使用 WCS，并显式验证或记录当前 UCS；
2. 允许按当前 UCS 输入参数，再显式转换到 WCS。

## 11. Z 坐标和三维实体问题

`Matrix3d.Scaling(scale, basepoint)` 是三维统一缩放。当前完整矩阵实际为：

```text
| s·cosθ  -s·sinθ  0  dx |
| s·sinθ   s·cosθ  0  dy |
|    0        0     s   0 |
|    0        0     0   1 |
```

所以：

```text
Z' = s·Z
```

使用当前正向比例：

```text
Z' = 0.999997425176·Z
```

如果图形单位是米，在 `Z=100m` 时：

```text
高程改变量约为 -0.000257m，即 -0.257mm
```

数值不大，但二维四参数平面转换通常期望：

```text
Z' = Z
```

因此：

- 全部对象位于 `Z=0` 时没有影响；
- 三维管线、地形、块参照和高程点会被改变；
- 使用同参数正反往返时可以恢复；
- 单独执行正向转换会永久改变高程；
- 如果比例参数只适用于平面，当前 Z 处理不合理。

若要求保留高程，应使用：

```text
| a  -b  0  dx |
| b   a  0  dy |
| 0   0  1   0 |
| 0   0  0   1 |
```

即只对 XY 使用比例和旋转，对 Z 使用恒等变换。

## 12. 与完整地理坐标系转换的区别

当前插件执行的是实体级仿射变换：

```text
移动 + 旋转 + 统一缩放
```

它不会处理：

- 坐标系代码和图形 CRS 元数据；
- 地图投影；
- 椭球和大地基准；
- 格网改正；
- 非线性区域改正；
- 大地转换路径；
- 坐标系有效范围；
- 源坐标系和目标坐标系自动反算。

AutoCAD Map 3D 官方推荐为源图形和目标图形分配坐标系，然后在查询对象时通过坐标系库执行转换。大地基准转换可以使用解析公式、格网文件或转换路径。

官方依据：

- [To Transform the Coordinate System of a Drawing](https://help.autodesk.com/cloudhelp/2025/ENU/MAP3D-Use/files/GUID-291991BF-31F1-46F0-A9E1-72A29B8E8C54.htm)
- [About Geodetic Transformations](https://help.autodesk.com/cloudhelp/2025/ENU/MAP3D-Use/files/GUID-CBFAC20A-F512-4D52-8663-D46DCAA83544.htm)
- [About Coordinate Systems](https://help.autodesk.com/cloudhelp/2023/ENU/MAP3D-Use/files/GUID-8ABA6E8F-17E9-4202-981C-67E45F2D61B8.htm)

所以当前插件适用的准确描述是：

```text
在有限区域内，对平面坐标执行二维四参数相似变换。
```

如果深圳独立坐标与目标平面坐标之间在项目区域内能够用四参数拟合，并且控制点残差满足工程要求，该算法是合理的。

如果涉及不同投影、不同大地基准或较大地理范围，不能只依赖这个矩阵。

## 13. 实体级副作用

`CoT` 和 `UCoT` 使用 DXF 组码 410=`Model` 选择模型空间全部实体，再逐个调用 `Entity.TransformBy`。

统一缩放会同时影响：

- 线段和多段线长度；
- 圆和圆弧半径；
- 文字高度；
- 标注和引线几何；
- 块参照位置、旋转和比例；
- 外部参照块的插入变换；
- 三维实体尺寸；
- 非零 Z 高程。

这与“整体缩放图形”的语义一致，但不一定符合“只变换坐标、保持标注外观和高程不变”的产品需求。

此外，每个实体的 AutoCAD 异常被单独捕获，循环结束后仍执行 `trans.Commit()`。如果某个代理实体、特殊标注或其他对象拒绝变换，最终可能形成：

```text
部分实体：新坐标
部分实体：旧坐标
```

对于全图坐标转换，这种部分成功状态比矩阵公式本身更危险。

## 14. 准确性评价

| 检查项 | 结论 |
| --- | --- |
| `PreMultiplyBy` 使用顺序 | 正确 |
| 正向二维四参数公式 | 正确 |
| 同参数恢复矩阵 | 正确，是严格逆矩阵 |
| 当前默认 `CoT→UCoT` | 不严格可逆 |
| 旋转角单位 | 正确，使用弧度 |
| AutoCAD 旋转方向 | 正确，WCS 正 Z 下正角逆时针 |
| `DX/DY` 含义 | 实际是仿射平移项，但变量名和配置未明确 |
| WCS 参数假设 | 内部一致，但没有显式校验 |
| 当前 UCS 支持 | 不支持，也不参与参数换算 |
| 二维 XY 处理 | 合理 |
| Z 坐标处理 | 可疑，会被同比例缩放 |
| 完整 CRS/大地转换 | 不支持 |
| 参数物理精度 | 缺少控制点资料，无法确认 |
| 单实体失败回滚 | 不合理，存在部分提交风险 |

## 15. 推荐重构

### 15.1 直接表达标准正向矩阵

当前写法虽然正确，但依赖同一个 `basepoint` 在三种矩阵中的抵消关系，不容易审查。

建议在世界原点直接构造：

```csharp
Matrix3d scaleMatrix =
    Matrix3d.Scaling(scale, Point3d.Origin);

Matrix3d rotationMatrix =
    Matrix3d.Rotation(angle, Vector3d.ZAxis, Point3d.Origin);

Matrix3d displacementMatrix =
    Matrix3d.Displacement(Point3d.Origin.GetVectorTo(offset));

Matrix3d forward = displacementMatrix
    .PostMultiplyBy(rotationMatrix)
    .PostMultiplyBy(scaleMatrix);
```

这会直接表达：

```text
M正 = T × R × S
```

### 15.2 直接使用逆矩阵

恢复时不应重复手工拼接反向参数，而应使用同一个正向矩阵：

```csharp
Matrix3d reverse = forward.Inverse();
```

这样可以避免：

- 正反向参数不一致；
- 符号写反；
- 矩阵乘法顺序漂移；
- 后续只修改一侧实现。

如果业务确实要求使用独立拟合的反向参数，应将命令命名和文档改为“独立反向拟合”，而不能宣称是严格恢复。

### 15.3 分离二维和三维需求

应明确配置：

```text
TransformZ=false
```

二维模式使用 `diag(s,s,1)`；只有在参数明确包含垂向尺度时才缩放 Z。

### 15.4 参数校验

构造矩阵前至少校验：

- 所有参数是有限数；
- `scale` 大于零且远离零；
- 角度单位明确为弧度；
- 配置所有字段一次性解析成功后再替换默认参数；
- 正反向使用同一参数版本；
- 配置文件记录源/目标坐标系和单位；
- 参数有效区域与当前图形范围相符。

### 15.5 事务原子性

推荐策略：

1. 转换前检查所有参数；
2. 先对代表性点和实体做预验证；
3. 任一实体失败则中止并回滚整个事务；
4. 输出失败对象 ID 和类型；
5. 提交前输出处理数量和最大坐标范围；
6. 操作前提醒保存或自动创建备份。

## 16. 参数资料要求

要判断转换是否具有工程精度，必须补齐：

```text
源坐标系名称和定义：
目标坐标系名称和定义：
图形单位：
X/Y 轴含义：
角度正方向：
角度起算轴：
DX/DY 的数学定义：
参数求解方法：
参与拟合的控制点：
独立检查点：
最大残差：
平面均方根误差：
参数有效区域：
是否转换 Z：
AutoCAD 版本：
参数责任人和确认日期：
```

`change.txt` 目前只有“四参数法提高精度”，不足以作为测绘精度依据。

## 17. 建议测试矩阵

### 17.1 纯数学测试

- 验证 `(0,0)` 映射到 `(DX,DY)`；
- 验证 `(1,0)` 和 `(0,1)` 的旋转、尺度和正负方向；
- 验证正向矩阵乘逆矩阵接近单位矩阵；
- 验证 `forward.Inverse()` 与手工逆公式一致；
- 验证不同坐标数量级下的浮点误差；
- 验证 `scale=0`、负比例、NaN 和无穷值被拒绝。

### 17.2 控制点测试

- 使用参与拟合的控制点验证残差；
- 使用未参与拟合的独立检查点验收；
- 记录最大误差、平均误差和均方根误差；
- 覆盖项目区域四角和中心；
- 与具有明确坐标系定义的软件或成果表交叉验证；
- 如具备 AutoCAD Map 3D，比较 `ADETRANSFORM` 或坐标系库结果。

### 17.3 WCS/UCS 测试

- 世界坐标系；
- 平移 UCS；
- 绕 Z 轴旋转 UCS；
- 倾斜 UCS；
- 验证固定 WCS 模式下结果不受当前 UCS 影响；
- 如果支持 UCS 参数，验证 UCS→WCS 转换正确。

### 17.4 Z 和实体测试

- Z=0 与非零 Z 点；
- 2D/3D 多段线；
- 圆、圆弧和样条曲线；
- 单行文字、多行文字和标注；
- 普通块、动态块和属性块；
- 外部参照；
- Civil 3D/代理实体；
- 三维实体和曲面；
- 任一对象失败时是否整体回滚。

### 17.5 往返测试

- 同一组参数 `CoT→UCoT`；
- 当前两组默认参数 `CoT→UCoT`；
- 重复执行两次 `CoT` 的防误操作检查；
- 重复执行两次 `UCoT` 的防误操作检查；
- 保存、关闭并重新打开 DWG 后检查坐标；
- 比较图层、块、标注和外参状态。

## 18. 最终评价

当前源码的矩阵推导比表面上看起来更合理：利用同一个 `basepoint` 构造平移、绕点旋转和绕点缩放，通过 `PreMultiplyBy` 的顺序最终得到标准的：

```text
P' = B + sR·P
```

因此不能简单地把现有矩阵顺序判定为错误。正向和恢复在同参数条件下是严格互逆的。

真正影响准确性和可维护性的因素是：

- 发布配置与源码契约不一致；
- 正反默认参数不同；
- `basepoint` 名称没有表达平移项语义；
- Z 被三维统一缩放；
- WCS 假设没有显式验证；
- 没有控制点和参数解算资料；
- 将平面相似变换称为“坐标系转换”容易与完整 CRS 转换混淆；
- 实体失败后仍提交事务。

在补齐控制点资料之前，只能确认“矩阵代数正确”，不能确认“坐标成果达到工程精度”。后续修改的正确顺序应是：

1. 固定源/目标坐标系和参数定义；
2. 建立控制点与黄金 DWG；
3. 修复配置和事务原子性；
4. 使用同一正向矩阵的 `Inverse()`；
5. 明确是否保留 Z；
6. 最后用 AutoCAD 和测绘成果进行验收。

## 19. Autodesk 官方参考

- [Matrix3d Structure](https://help.autodesk.com/cloudhelp/2024/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_Geometry_Matrix3d.html)
- [Matrix3d Methods](https://help.autodesk.com/view/OARX/2025/ENU/?guid=OARX-ManagedRefGuide-__MEMBERTYPE_Methods_Autodesk_AutoCAD_Geometry_Matrix3d)
- [Transform Objects (.NET)](https://help.autodesk.com/view/ACDLT/2026/ENU/?caas=caas%2Fdocumentation%2FACD%2F2014%2FENU%2Ffiles%2FGUID-D4348E23-7ECB-48F6-90B7-FB7EF42DFA8D-htm.html)
- [Rotate Objects (.NET)](https://help.autodesk.com/cloudhelp/2024/CHS/OARX-DevGuide-Managed/files/GUID-DAF76951-DD0C-413F-86A8-471E2B94C1C0.htm)
- [Matrix3d.Scaling Method](https://help.autodesk.com/cloudhelp/2022/ENU/OARX-ManagedRefGuide/files/OARX-ManagedRefGuide-Autodesk_AutoCAD_Geometry_Matrix3d_Scaling_double_Point3d.html)
- [Define a User Coordinate System (.NET)](https://help.autodesk.com/cloudhelp/2017/ITA/AutoCAD-NET/files/GUID-096085E3-5AD5-4454-BF10-C9177FDB5979.htm)
- [ADETRANSFORM (Transform Command)](https://help.autodesk.com/cloudhelp/2023/ENU/MAP3D-Use/files/GUID-AB726381-7DD2-49D0-9902-C1300C636A7C.htm)
- [To Transform the Coordinate System of a Drawing](https://help.autodesk.com/cloudhelp/2025/ENU/MAP3D-Use/files/GUID-291991BF-31F1-46F0-A9E1-72A29B8E8C54.htm)
- [About Coordinate Systems](https://help.autodesk.com/cloudhelp/2023/ENU/MAP3D-Use/files/GUID-8ABA6E8F-17E9-4202-981C-67E45F2D61B8.htm)
- [About Geodetic Transformations](https://help.autodesk.com/cloudhelp/2025/ENU/MAP3D-Use/files/GUID-CBFAC20A-F512-4D52-8663-D46DCAA83544.htm)
