// 把若干文件放到 macOS 剪贴板（和在 Finder 里选中后 ⌘C 一样），之后在微信里 ⌘V 就能一次发出去。
// 用法：osascript -l JavaScript 复制文件到剪贴板.js [--text 文字] 文件1 文件2 …（带 --text 时文字和文件一起放上去）
ObjC.import('AppKit');
function run(argv){
 const pb=$.NSPasteboard.generalPasteboard;pb.clearContents;
 const list=$.NSMutableArray.alloc.init;
 if(argv[0]==='--text'){list.addObject($(argv[1]));argv=argv.slice(2)}
 argv.forEach(p=>list.addObject($.NSURL.fileURLWithPath(p)));
 if(!pb.writeObjects(list))return 'fail';
 // 再加一份老格式的“文件列表”（Finder ⌘C 多个文件时也会放这个）：有的 App（微信）只认这个，不加就只粘出一部分
 if(argv.length)pb.setPropertyListForType($(argv),'NSFilenamesPboardType');
 return 'ok';
}
