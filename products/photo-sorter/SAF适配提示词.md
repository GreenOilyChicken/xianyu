# SAF 适配提示词（给 Cursor）

> 已确认：安卓 file_picker 选目录返回的是 `content://` tree URI，dart:io 读不了。
> **扫描范围已定 C：全照片格式 + 视频**，元数据读取换用 `media_metadata_plus`（Rust 底层，一个包覆盖 JPEG/HEIC/MP4/MOV 等）。
> 用这套提示词让 Cursor 实现安卓 SAF content URI 适配，收尾功能2。
> 一段一段丢给 Cursor，按顺序执行。

---

## 提示词 0：开工前小验证（必做，先于一切）

```
开工前先做一个小验证，决定后续 SAF 适配走向。

【任务】
在安卓上，file_picker 选目录会返回 content:// tree URI。
我要用 media_metadata_plus 包读照片/视频的 GPS 元数据，但它的 API 是 MediaMetadata.read(path)，吃文件路径。

验证一件事：MediaMetadata.read() 能否直接接受 content:// URI？

写一个最简测试：
1. flutter pub add media_metadata_plus
2. 安卓上用 file_picker 选一张照片（拿到 content:// 单文件 URI，不是 tree URI）
3. 调 await MediaMetadata.read(contentUri) 试试
4. 打印结果：能拿到 meta?.gps?.lat 说明能吃 content URI；报错或返回 null 说明不能

【根据结果分两条路】
- 能直接吃 content URI：后续 SAF 适配简单，listImages 列出来的 content URI 直接传给 read()
- 不能吃：要在 Kotlin 侧加一个方法，把 content URI 转成临时文件路径（拷到 app 缓存目录），再传给 read()

这个验证只写个 main 里的临时测试函数，不进正式代码，验证完告诉我结果，我再给后续提示词。
```

---

## 提示词 1：抽象 PhotoSource 接口 + 改造 PhotoClassifier + 换元数据包

```
现在要给照片分类功能加安卓 SAF 适配。先做第一步：抽象"照片源"，让核心分类逻辑不关心照片来自文件路径还是 content URI。

【重要：换元数据读取包】
原方案用 exif 包，但它只支持 JPEG，不支持 HEIC 和视频。
现在改用 media_metadata_plus 包（pubspec 加 media_metadata_plus: ^1.5.1），它一个包覆盖：
- JPEG/HEIC/PNG/WebP/RAW 全照片格式
- MP4/MOV 视频
- 统一从 meta?.gps?.lat / meta?.gps?.lon 取 GPS
- API：await MediaMetadata.read(path) → MediaMetadata? （不支持或损坏返回 null）
注意：开发机要装 Rust 工具链（rustup）才能 build，因为底层是 Rust。

【现状】
- lib/core/classify/photo_classifier.dart 的 classifyAndArchive(...) 现在直接用 dart:io 的 File 读取照片（读 EXIF、复制到输出目录）
- 安卓上选目录返回的是 content:// tree URI，dart:io 的 File 读不了

【任务】
1. 改造 lib/core/exif/photo_metadata_reader.dart：
   - 从用 exif 包改为用 media_metadata_plus
   - readGps(Photo photo) → (lat, lon) 或 null：调 MediaMetadata.read(photo.path)，取 meta?.gps?.lat / lon
   - readDateTime(Photo photo) → DateTime?：取 meta?.capturedAt
   - 注意：read() 接收的是路径字符串，桌面端直接给文件路径即可

2. 在 lib/core/classify/ 新建 photo_source.dart，定义抽象接口：

   abstract class PhotoSource {
     /// 给元数据读取用的路径或 URI（桌面=文件路径，安卓可能要转临时文件，见提示词0验证结果）
     Future<String> resolveMetadataPath(Photo photo);
     /// 把照片复制到输出路径（归档用）
     Future<void> copyTo(Photo photo, String destPath);
   }

3. 改造 lib/core/classify/photo_classifier.dart 的 classifyAndArchive：
   - 方法签名加一个参数：classifyAndArchive(List<Photo> photos, String outputRoot, PhotoSource source, {onProgress, isCancelled})
   - 内部所有"读 EXIF"改为：先 source.resolveMetadataPath(photo) 拿到路径，再调 PhotoMetadataReader.readGps
   - 内部所有"复制文件到输出目录"改为调 source.copyTo(photo, destPath)
   - 核心分类/归档逻辑、目录规划、无GPS归"未定位/" 这些都不变

4. 新建 lib/core/classify/file_photo_source.dart：
   class FilePhotoSource implements PhotoSource {
     // 桌面实现：用 dart:io 的 File
     // resolveMetadataPath：直接返回 photo.path（文件路径就是元数据路径）
     // copyTo：File.copy
   }
   这是桌面端的原有实现，抽出来只是为了和安卓实现同级

5. 更新 classify_providers.dart：
   - 桌面端创建 FilePhotoSource 注入 PhotoClassifier
   - 安卓端先占位（下一步实现 SafPhotoSource）

【要求】
- core/ 下不引用任何平台插件，保持纯 Dart（media_metadata_plus 是 Flutter 插件，但 photo_metadata_reader 只调它的 read()，不直接碰平台 API；如果 media_metadata_plus 被认定为平台插件，把它包一层抽象接口，core 调抽象）
- 改造后 flutter test 仍要通过（已有测试可能要相应改 mock 的 PhotoSource 和 mock 掉 MediaMetadata.read）
- 不破坏现有的 classify() 只规划路径不落地的行为
- 桌面端行为完全不变，只是多了一层抽象
- listImages/扫描器的过滤要放宽：不再只过滤 jpg，而是 image/* + video/mp4 + video/quicktime，靠 media_metadata_plus 用 magic bytes 判断格式（不看扩展名）
```

---

## 提示词 2：Kotlin 侧实现 SAF 访问（MethodChannel）

```
第二步：安卓原生侧实现 SAF 访问，通过 MethodChannel 暴露给 Dart。

【背景】media_metadata_plus 的 MediaMetadata.read(path) 吃文件路径，不吃 content:// URI。
若提示词0验证发现它不能直接吃 content URI，就需要在 Kotlin 侧把 content URI 转成临时文件路径再交给 Dart。

【任务】
在 android/app/src/main/kotlin/ 下新建一个 Plugin（或加在 MainActivity 里），注册 MethodChannel "photo_sorter_saf"，实现三个方法：

1. listImages(String treeUriString) → List<Map>
   - 输入：file_picker 返回的 content:// tree URI 字符串
   - 用 contentResolver + DocumentsContract.getChildDocuments 遍历该 tree 下所有文档
   - ★过滤放宽（不再只 image/jpeg）：用 MIME_TYPE 列查询匹配 image/* 和 video/mp4 和 video/quicktime
   - 返回每张照片的：{ uri: String, name: String, size: Long, date: Long, mimeType: String }
   - date 是拍摄/修改时间（LAST_MODIFIEDDATE 列），毫秒时间戳
   - 注意性能：用 Cursor 查询，别一张张开流
   - 子目录递归：DocumentsContract.getChildDocuments 默认只列一层，要递归子 tree（用 DocumentsContract.findDocument 遍历子 tree）

2. resolveMetadataPath(String uriString) → String
   - 输入：单张照片/视频的 content URI
   - 作用：把 content URI 转成 media_metadata_plus 能读的路径
   - 实现：用 contentResolver.openInputStream(uri) 读流，拷到 app 缓存目录（getCacheDir + 唯一文件名），返回临时文件路径
   - ★性能优化：大视频别整个拷，先拷一个能拿元数据的头部即可——但 media_metadata_plus 可能要完整文件，先做完整拷贝跑通，性能优化后续（或用 isPrefetch 选项）
   - 拷完返回路径给 Dart，Dart 调 MediaMetadata.read(临时路径)
   - 用完要清理临时文件（Dart 侧读完通知 Kotlin 删，或定期清）

3. copyTo(String uriString, String destPath) → bool
   - 输入：照片 content URI + 目标本地路径（dart:io 能写的路径，如 app 专属目录）
   - openInputStream(uri) 读，写到 FileOutputStream(destPath)
   - 返回是否成功
   - 大文件（尤其视频）要流式拷贝，别一次性读进内存

【实现要点】
- 在 MainActivity.configureFlutterEngine 里注册 channel
- 方法都要在后台线程跑（用 thread 或 coroutine），别阻塞 platform 线程
- 参数校验：uri 为空或打不开流要返回错误，别让 app 崩
- listImages 性能关键：几百张/视频要快，用 projection 只查需要的列
- 临时文件路径要稳定可清理：放 getCacheDir()/photo_sorter_tmp/ 下，文件名用 uri 哈希

【不要做】
- 不要在 Kotlin 侧解析元数据内容（media_metadata_plus 已经做这事，Kotlin 只负责把 URI 转成它能读的路径）
- 不要申请 READ_EXTERNAL_STORAGE 权限（SAF tree URI 自带读权限）
- 不要在 listImages 阶段就拷文件（那会很慢；listImages 只列清单，拷贝在 resolveMetadataPath 按需做）
```

---

## 提示词 3：Dart 侧 SafPhotoSource + 接入

```
第三步：Dart 侧实现 SafPhotoSource，接入工厂，完成适配。

【任务】
1. 新建 lib/data/services/saf_photo_source.dart：

   class SafPhotoSource implements PhotoSource {
     static const _channel = MethodChannel('photo_sorter_saf');

     @override
     Future<String> resolveMetadataPath(Photo photo) async {
       // photo.path 存的是 content:// 单文件 URI
       // 让 Kotlin 把它转成 media_metadata_plus 能读的临时文件路径
       final tmpPath = await _channel.invokeMethod('resolveMetadataPath', {
         'uriString': photo.path,
       });
       return tmpPath as String;
     }

     @override
     Future<void> copyTo(Photo photo, String destPath) async {
       await _channel.invokeMethod('copyTo', {
         'uriString': photo.path,
         'destPath': destPath,
       });
     }
   }

2. 新建 lib/data/services/saf_directory_scanner.dart，实现 DirectoryPickerService 返回的安卓路径扫描：
   - 接收 file_picker 返回的 content:// tree URI
   - 调 MethodChannel 'listImages' 拿到照片/视频列表
   - 把每项封装成 Photo 对象，path 字段存该文件的 content:// URI（不是文件路径）
   - 返回 List<Photo>，以及总数、含 GPS 数
   - ★扫描阶段只列清单不读元数据（GPS 数要靠 resolveMetadataPath + MediaMetadata.read 判断，扫描时先不判，分类时才读）

3. 改 directory_picker_factory.dart：
   - 桌面：返回 FileDirectoryScanner + FilePhotoSource（原有）
   - 安卓：返回 SafDirectoryScanner + SafPhotoSource（新增）
   - 按 Platform.isAndroid 分流，工厂逻辑别散落到业务页

4. 改 classify_view_model.dart：
   - 扫描阶段：调注入的 DirectoryScanner（桌面是文件扫描，安卓是 SAF 扫描）
   - 分类阶段：把注入的 PhotoSource 传给 photoClassifier.classifyAndArchive
   - ViewModel 不感知 SAF 存在，只通过抽象接口调

5. 输出目录策略（重要，省一半工作量）：
   - 安卓默认输出到 app 专属目录（path_provider 的 getExternalStorageDirectory 或 getApplicationDocumentsDirectory）
   - 这个目录 dart:io 能直接写，不用走 SAF 写流
   - 用户分类完，UI 上"打开目录"按钮在安卓上用 ACTION_VIEW 或 share intent 引导
   - 桌面端输出目录选择保持不变

6. 临时文件清理：
   - resolveMetadataPath 在 Kotlin 侧会往 app 缓存目录拷临时文件
   - 分类完成后（或每个文件读完元数据后）通知 Kotlin 清理，或用系统缓存机制（app 内存低时自动清）

【要求】
- 桌面端代码一行不改（FilePhotoSource + FileDirectoryScanner 就是原来逻辑的抽取）
- 安卓端通过 MethodChannel 调 Kotlin，不直接用 dart:io 读 content://
- core/ 仍然纯 Dart（media_metadata_plus 如果算平台插件，在 photo_metadata_reader 包一层抽象，core 调抽象）
- 改完 flutter test 通过
- 在安卓真机上跑一次：选相册所在目录 → 扫描 → 分类 → 看归档结果是否正确

【验收点】
- 选 SAF 目录后扫描能列出里面的图片和视频（jpg/heic/mp4/mov）
- 有 GPS 的照片/视频归到对应省目录
- 无 GPS 的归到"未定位/"
- 输出在 app 专属目录下能找到分类后的文件夹结构
- 视频元数据能正确读取 GPS（mp4/mov 都测）
- HEIC 照片元数据能正确读取 GPS
```

---

## 执行顺序与验证

按 0 → 1 → 2 → 3 顺序丢给 Cursor，每段跑完验证：

| 步骤 | 跑完验证什么 | 通过标准 |
|---|---|---|
| 0 | 安卓 content URI 试 MediaMetadata.read() | 确认能否直接吃，决定提示词2/3 走哪条路 |
| 1 | `flutter test` | 现有测试通过，桌面行为不变，listImages 过滤放宽 |
| 2 | 安卓 `flutter run`，选目录后打印 listImages 返回 | 能列出图片+视频，不崩 |
| 3 | 安卓真机端到端：选目录→扫描→分类 | 照片+视频按省归档到 app 目录，无 GPS 归未定位 |

## 如果遇到问题

- **listImages 列不出文件**：检查 tree URI 是否带 `/tree/`，file_picker 选目录返回的格式可能是 `content://com.android.externalstorage.documents/tree/primary%3ADCIM`，URL 编码要对
- **MediaMetadata.read(contentUri) 报错**：说明它不认 content URI，走提示词2的 resolveMetadataPath 转临时文件
- **视频 GPS 读不到**：有些视频根本没拍 GPS（非手机拍的），这正常归"未定位"；确认是手机拍的 mp4 再排查
- **HEIC 读不到 GPS**：极少数老 HEIC 格式元数据异常，归"未定位"即可
- **性能慢（视频拷临时文件）**：大视频完整拷很慢，优化方向是只拷元数据所在头部，但 media_metadata_plus 可能要完整文件；先用完整拷跑通，性能后续优化
- **copyTo 写不进去**：destPath 必须是 app 能写的目录（app 专属），不能写任意外部路径
- **listImages 几百张要卡**：确认 Kotlin 侧在后台线程跑，用 Cursor 批量查而不是逐张开流
```
