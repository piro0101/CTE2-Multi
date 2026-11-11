using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Net;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace Cte2Patcher {
    public class PatchFile { public string path {get;set;} public string sha256 {get;set;} public long bytes {get;set;} }
    public class Package { public string url {get;set;} public string sha256 {get;set;} public long bytes {get;set;} public List<PatchFile> files {get;set;} }
    public class Release { public int schema {get;set;} public string release_id {get;set;} public string minimum_patcher {get;set;} public string notes {get;set;} public Dictionary<string,Package> packages {get;set;} }
    public class Change { public string path {get;set;} public bool existed {get;set;} public string before {get;set;} public string after {get;set;} public string staged {get;set;} }
    public class Journal { public string root {get;set;} public string backup {get;set;} public string phase {get;set;} public List<Change> changes {get;set;} }
    public class Preferences { public string folder {get;set;} public string launcher {get;set;} public bool korean {get;set;} public string profile {get;set;} }
    public static class Engine {
        static Engine(){AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling",false);AppContext.SetSwitch("Switch.System.IO.BlockLongPaths",false);}
        public const string Version="1.1.0";
        public const string Feed="https://github.com/piro0101/CTE2-Multi/releases/latest/download/update.json";
        public const string Guide="https://github.com/piro0101/CTE2-Multi#readme";
        public static readonly JavaScriptSerializer Json=new JavaScriptSerializer {MaxJsonLength=8*1024*1024};
        static readonly string[] Roots={"mods","config","defaultconfigs","kubejs","patchouli_books","resourcepacks"};
        public static string Hash(byte[] bytes){using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();}
        public static string HashFile(string path){using(var stream=File.OpenRead(path))using(var sha=SHA256.Create())return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-","").ToLowerInvariant();}
        public static string Child(string root,string relative,bool option=false){
            if(string.IsNullOrEmpty(relative)||relative.Contains('\\')||relative.Contains(':')||relative.StartsWith("/")||Path.IsPathRooted(relative))throw new InvalidDataException("허용되지 않는 파일 경로입니다.");
            var parts=relative.Split('/');
            if(parts.Any(p=>string.IsNullOrEmpty(p)||p=="."||p==".."||p.EndsWith(".")||p.EndsWith(" ")||p.IndexOfAny(Path.GetInvalidFileNameChars())>=0||Regex.IsMatch(p,@"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)",RegexOptions.IgnoreCase)))throw new InvalidDataException("안전하지 않은 파일 경로입니다.");
            if(!(option&&relative=="options.txt")&&!Roots.Contains(parts[0]))throw new InvalidDataException("패치는 게임 모드·설정 폴더만 변경할 수 있습니다.");
            return Contained(root,relative);
        }
        static string Contained(string root,string relative){
            root=Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);string full=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
            if(!full.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("게임 폴더를 벗어나는 경로입니다.");
            for(string p=full;!string.IsNullOrEmpty(p)&&p.Length>=root.Length;p=Path.GetDirectoryName(p))if((Directory.Exists(p)||File.Exists(p))&&(File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)throw new IOException("연결된 폴더 대신 실제 게임 폴더를 선택하세요.");
            // GDLauncher paths plus datapack names routinely exceed MAX_PATH.
            // Extended paths avoid requiring an OS-wide registry change.
            if(full.StartsWith(@"\\?\"))return full;
            if(full.StartsWith(@"\\"))return @"\\?\UNC\"+full.Substring(2);
            return @"\\?\"+full;
        }
        static WebClient Client(){ServicePointManager.SecurityProtocol=SecurityProtocolType.Tls12;var c=new WebClient();c.Encoding=Encoding.UTF8;c.Headers[HttpRequestHeader.UserAgent]="CTE2-Patcher/"+Version;c.Headers[HttpRequestHeader.CacheControl]="no-cache";return c;}
        static Uri Trusted(string url){Uri u;if(!Uri.TryCreate(url,UriKind.Absolute,out u)||u.Scheme!="https"||u.Host!="github.com"||!u.AbsolutePath.StartsWith("/piro0101/CTE2-Multi/releases/",StringComparison.Ordinal))throw new InvalidDataException("공식 패치 저장소 주소가 아닙니다.");return u;}
        public static async Task<Release> Latest(){
            using(var c=Client()){
                string data=await c.DownloadStringTaskAsync(Trusted(Feed));if(data.Length>8*1024*1024)throw new InvalidDataException("업데이트 정보가 너무 큽니다.");
                var release=Json.Deserialize<Release>(data);Validate(release);return release;
            }
        }
        public static void Validate(Release release){
            if(release==null||release.schema!=1||!Regex.IsMatch(release.release_id??"",@"^[a-zA-Z0-9._-]{1,64}$")||release.packages==null)throw new InvalidDataException("업데이트 정보 형식이 올바르지 않습니다.");
            System.Version minimum;if(!System.Version.TryParse(release.minimum_patcher,out minimum)||minimum>new System.Version(Version))throw new InvalidDataException("새 패치기가 필요합니다. 안내 페이지에서 최신 패치기를 내려받으세요.");
            if(!release.packages.ContainsKey("client"))throw new InvalidDataException("플레이어 패치가 누락되었습니다.");
            foreach(var role in release.packages.Keys){
                if(role!="client"&&role!="server")throw new InvalidDataException("알 수 없는 패치 종류입니다.");
                if(!release.packages.ContainsKey(role))throw new InvalidDataException("패치 종류가 누락되었습니다.");var p=release.packages[role];Trusted(p.url);
                if(p.bytes<1||p.bytes>128*1024*1024||!Regex.IsMatch(p.sha256??"",@"^[a-f0-9]{64}$")||p.files==null||p.files.Count<1||p.files.Count>4096)throw new InvalidDataException("패치 크기·검증 정보가 올바르지 않습니다.");
                var paths=new HashSet<string>(StringComparer.OrdinalIgnoreCase);long total=0;
                foreach(var f in p.files){Child(Path.GetTempPath(),f.path);if(!paths.Add(f.path)||f.bytes<0||f.bytes>128*1024*1024||!Regex.IsMatch(f.sha256??"",@"^[a-f0-9]{64}$"))throw new InvalidDataException("중복되거나 잘못된 패치 파일입니다.");total=checked(total+f.bytes);}
                if(total>256*1024*1024)throw new InvalidDataException("압축 해제 크기가 허용 범위를 넘습니다.");
            }
        }
        public static string ExpandFolder(string folder){
            if(string.IsNullOrWhiteSpace(folder))throw new IOException("게임 폴더 경로를 입력하거나 선택하세요.");
            return Path.GetFullPath(Environment.ExpandEnvironmentVariables(folder.Trim().Trim('"')));
        }
        public static string NormalizeFolder(string folder){
            string root=ExpandFolder(folder);
            if(!Directory.Exists(Path.Combine(root,"mods"))&&Directory.Exists(Path.Combine(root,"instance","mods")))root=Path.Combine(root,"instance");
            if(!Directory.Exists(Path.Combine(root,"mods"))||!Directory.GetFiles(Path.Combine(root,"mods"),"Mine_and_Slash-1.20.1-6.4.13.jar").Any())throw new IOException("CTE2 2.1.4가 먼저 설치된 게임 폴더를 선택하세요. mods 폴더가 보이는 위치입니다.");
            return root;
        }
        public static List<PatchFile> Needed(string root,Package package){return package.files.Where(f=>{string p=Child(root,f.path);return !File.Exists(p)||new FileInfo(p).Length!=f.bytes||HashFile(p)!=f.sha256;}).ToList();}
        static void WriteAtomic(string path,byte[] data){
            Directory.CreateDirectory(Path.GetDirectoryName(path));string temp=path+".cte2-"+Guid.NewGuid().ToString("N")+".tmp";
            using(var stream=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){stream.Write(data,0,data.Length);stream.Flush(true);}
            if(File.Exists(path))File.Replace(temp,path,null);else File.Move(temp,path);
        }
        static void SaveJournal(string path,Journal journal){WriteAtomic(path,Encoding.UTF8.GetBytes(Json.Serialize(journal)));}
        static string Area(string root){return Contained(root,".cte2-patcher");}
        static void CheckClosed(IEnumerable<string> files){foreach(string p in files.Distinct(StringComparer.OrdinalIgnoreCase))if(File.Exists(p))using(File.Open(p,FileMode.Open,FileAccess.Read,FileShare.None)){} }
        public static byte[] KoreanOptions(byte[] original){
            string text=Encoding.UTF8.GetString(original).TrimStart('\ufeff');var lines=text.Replace("\r\n","\n").Split('\n').ToList();var packs=new List<string>();int index=lines.FindIndex(x=>x.StartsWith("resourcePacks:"));
            if(index>=0){try{packs=Json.Deserialize<List<string>>(lines[index].Substring("resourcePacks:".Length))??new List<string>();}catch{throw new InvalidDataException("기존 리소스팩 설정을 읽을 수 없습니다. 원본 설정은 보존했습니다.");}}
            foreach(string p in new[]{"file/CTE2-2.1.4-한글패치.zip","file/CTE2-2.1.4-KR-Addon.zip"}){packs.RemoveAll(x=>x==p);packs.Add(p);}
            string line="resourcePacks:"+Json.Serialize(packs);if(index<0)lines.Add(line);else lines[index]=line;
            index=lines.FindIndex(x=>x.StartsWith("lang:"));if(index<0)lines.Add("lang:ko_kr");else lines[index]="lang:ko_kr";
            return new UTF8Encoding(false).GetBytes(string.Join("\n",lines));
        }
        public static void Recover(string root,Action<string> log){
            string file=Path.Combine(Area(root),"pending.json");if(!File.Exists(file))return;
            var j=Json.Deserialize<Journal>(File.ReadAllText(file,Encoding.UTF8));if(j==null||Path.GetFullPath(j.root)!=Path.GetFullPath(root)||j.changes==null||!j.backup.StartsWith("backups/")||j.backup.Contains(".."))throw new IOException("이전 패치 복구 기록을 운영자에게 확인받으세요.");
            string backup=Contained(Area(root),j.backup);
            if(j.phase=="complete"){File.Move(file,file+".completed-"+Guid.NewGuid().ToString("N"));return;}
            foreach(var e in j.changes){string target=Child(root,e.path,true);if(File.Exists(target)){string hash=HashFile(target);if(hash!=e.after&&(!e.existed||hash!=e.before))throw new IOException("업데이트 중 다른 프로그램이 파일을 변경했습니다. 백업을 보존하고 중단합니다: "+e.path);}if(e.existed&&(!File.Exists(Child(backup,e.path,true))||HashFile(Child(backup,e.path,true))!=e.before))throw new IOException("복원할 백업이 손상되었습니다.");}
            CheckClosed(j.changes.Select(e=>Child(root,e.path,true)));
            foreach(var e in j.changes.AsEnumerable().Reverse()){string target=Child(root,e.path,true);if(e.existed){if(!File.Exists(target)||HashFile(target)!=e.before)WriteAtomic(target,File.ReadAllBytes(Child(backup,e.path,true)));}else if(File.Exists(target)){string saved=Contained(backup,"new-files/"+e.path);Directory.CreateDirectory(Path.GetDirectoryName(saved));File.Move(target,saved);}}
            File.Move(file,file+".recovered-"+Guid.NewGuid().ToString("N"));log("이전 미완료 업데이트를 백업 상태로 복구했습니다.");
        }
        public static void InstallBytes(string root,Release release,string role,byte[] archive,bool korean,Action<string> log){
            Validate(release);var p=release.packages[role];if(archive.LongLength!=p.bytes||Hash(archive)!=p.sha256)throw new InvalidDataException("다운로드 검증에 실패했습니다. 설치하지 않았습니다.");
            string area=Area(root);Directory.CreateDirectory(area);using(var guard=new FileStream(Path.Combine(area,"update.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None)){
                Recover(root,log);string stamp=DateTime.Now.ToString("yyyyMMdd-HHmmss")+"-"+Guid.NewGuid().ToString("N").Substring(0,8);string backup=Contained(area,"backups/"+stamp);Directory.CreateDirectory(backup);
                string stage=Contained(area,"staging/"+stamp);Directory.CreateDirectory(stage);var changes=new List<Change>();
                using(var zip=new ZipArchive(new MemoryStream(archive),ZipArchiveMode.Read)){
                    if(zip.Entries.Count!=p.files.Count)throw new InvalidDataException("패치 목록과 압축 내용이 다릅니다.");var seen=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    foreach(var entry in zip.Entries){Child(root,entry.FullName);if(!seen.Add(entry.FullName))throw new InvalidDataException("중복 압축 경로입니다.");var expected=p.files.SingleOrDefault(f=>f.path==entry.FullName);if(expected==null||entry.Length!=expected.bytes)throw new InvalidDataException("목록에 없는 압축 파일입니다.");string path=Child(stage,entry.FullName);Directory.CreateDirectory(Path.GetDirectoryName(path));using(var input=entry.Open())using(var output=File.Create(path)){var buffer=new byte[65536];long total=0;int count;while((count=input.Read(buffer,0,buffer.Length))>0){total+=count;if(total>expected.bytes)throw new InvalidDataException("압축 파일이 허용 크기를 넘습니다.");output.Write(buffer,0,count);}if(total!=expected.bytes)throw new InvalidDataException("압축 파일 크기가 다릅니다.");}if(HashFile(path)!=expected.sha256)throw new InvalidDataException("개별 파일 검증에 실패했습니다.");string target=Child(root,entry.FullName);if(!File.Exists(target)||HashFile(target)!=expected.sha256)changes.Add(new Change{path=entry.FullName,existed=File.Exists(target),after=expected.sha256,staged=path});}
                }
                if(role=="client"&&korean){string target=Child(root,"options.txt",true),staged=Child(stage,"options.txt",true);byte[] original=File.Exists(target)?File.ReadAllBytes(target):new byte[0],adjusted=KoreanOptions(original);if(!original.SequenceEqual(adjusted)){File.WriteAllBytes(staged,adjusted);changes.Add(new Change{path="options.txt",existed=File.Exists(target),after=Hash(adjusted),staged=staged});}}
                // Quarantine the old enabled advancement and duplicate owned addon JARs; never touch unrelated mods.
                var obsolete=new List<string>{"config/openloader/data/cte_configuration/data/cte2/advancements/bounty_hunting/novice_miner.json"};
                foreach(string prefix in new[]{"CTE2-Multiplayer-","CTE2-Inspector-","CTE2-StepUp-Compat-","stepitup-","smartsprint-forge-","caramelChat-","fullbright-"})foreach(string file in Directory.GetFiles(Path.Combine(root,"mods"),prefix+"*.jar")){string relative="mods/"+Path.GetFileName(file);if(!p.files.Any(f=>f.path.Equals(relative,StringComparison.OrdinalIgnoreCase))&&p.files.Any(f=>f.path.StartsWith("mods/"+prefix,StringComparison.OrdinalIgnoreCase)))obsolete.Add(relative);}
                foreach(string path in obsolete)if(File.Exists(Child(root,path)))changes.Add(new Change{path=path,existed=true,after="",staged=""});
                CheckClosed(changes.Select(e=>Child(root,e.path,true)).Concat(p.files.Where(f=>f.path.EndsWith(".jar")||f.path.EndsWith(".zip")).Select(f=>Child(root,f.path))));
                foreach(var e in changes)if(e.existed){string source=Child(root,e.path,true);e.before=HashFile(source);string saved=Child(backup,e.path,true);Directory.CreateDirectory(Path.GetDirectoryName(saved));File.Copy(source,saved);}
                var j=new Journal{root=root,backup="backups/"+stamp,phase="applying",changes=changes};string journal=Path.Combine(area,"pending.json");SaveJournal(journal,j);
                try{
                    foreach(var e in changes){string target=Child(root,e.path,true);if(e.existed&&HashFile(target)!=e.before)throw new IOException("게임 파일이 변경되었습니다. 게임을 완전히 종료하세요.");if(e.staged.Length==0){string saved=Contained(backup,"quarantine/"+e.path);Directory.CreateDirectory(Path.GetDirectoryName(saved));File.Move(target,saved);}else WriteAtomic(target,File.ReadAllBytes(e.staged));log("적용: "+e.path);}
                    if(Needed(root,p).Count!=0)throw new IOException("설치 후 파일 검증에 실패했습니다.");
                    WriteAtomic(Path.Combine(area,"installed.json"),Encoding.UTF8.GetBytes(Json.Serialize(new{release_id=release.release_id,profile=role,installed_at=DateTimeOffset.Now.ToString("o")})));j.phase="complete";SaveJournal(journal,j);Recover(root,log);log("최신 패치 "+release.release_id+" 적용 완료.");
                }catch{Recover(root,log);throw;}
            }
        }
        public static async Task Apply(string root,Release release,string role,bool korean,Action<string> log){
            root=NormalizeFolder(root);Recover(root,log);var p=release.packages[role];byte[] bytes;log("패치를 내려받고 검증하고 있습니다.");using(var c=Client())bytes=await c.DownloadDataTaskAsync(Trusted(p.url));await Task.Run(()=>InstallBytes(root,release,role,bytes,korean,log));
        }
    }
    public static class ExplorerFolderPicker {
        // Windows common item dialog. Keep COM methods in native vtable order.
        [ComImport,Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")]
        class FileOpenDialog {}
        [ComImport,Guid("D57C7288-D4AD-4768-BE02-9D969532D960"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IFileOpenDialog {
            [PreserveSig] int Show(IntPtr owner);
            void SetFileTypes(uint count,IntPtr specs);void SetFileTypeIndex(uint index);void GetFileTypeIndex(out uint index);
            void Advise(IntPtr events,out uint cookie);void Unadvise(uint cookie);void SetOptions(uint options);void GetOptions(out uint options);
            void SetDefaultFolder(IShellItem folder);void SetFolder(IShellItem folder);void GetFolder(out IShellItem folder);void GetCurrentSelection(out IShellItem item);
            void SetFileName([MarshalAs(UnmanagedType.LPWStr)]string name);void GetFileName([MarshalAs(UnmanagedType.LPWStr)]out string name);
            void SetTitle([MarshalAs(UnmanagedType.LPWStr)]string title);void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)]string text);void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)]string text);
            void GetResult(out IShellItem item);void AddPlace(IShellItem item,uint location);void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)]string extension);
            void Close(int result);void SetClientGuid(ref Guid guid);void ClearClientData();void SetFilter(IntPtr filter);void GetResults(out IntPtr items);void GetSelectedItems(out IntPtr items);
        }
        [ComImport,Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"),InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
        interface IShellItem {
            void BindToHandler(IntPtr bind,ref Guid handler,ref Guid iid,out IntPtr result);void GetParent(out IShellItem parent);
            void GetDisplayName(uint format,out IntPtr name);void GetAttributes(uint mask,out uint attributes);void Compare(IShellItem other,uint hint,out int order);
        }
        [DllImport("shell32.dll",CharSet=CharSet.Unicode,PreserveSig=false)]
        static extern void SHCreateItemFromParsingName(string path,IntPtr bind,ref Guid iid,[MarshalAs(UnmanagedType.Interface)]out IShellItem item);
        public static string Pick(IWin32Window owner,string initial){
            var dialog=(IFileOpenDialog)new FileOpenDialog();IShellItem item=null,folder=null;IntPtr name=IntPtr.Zero;
            try{
                uint options;dialog.GetOptions(out options);dialog.SetOptions(options|0x20u|0x40u|0x800u|0x8u|0x2000000u);
                dialog.SetTitle("CTE2 게임 폴더 선택 · 주소창에 %appdata% 입력 가능");dialog.SetOkButtonLabel("이 폴더 선택");
                if(!string.IsNullOrWhiteSpace(initial)){
                    string path=Engine.ExpandFolder(initial);
                    if(Directory.Exists(path)){Guid iid=typeof(IShellItem).GUID;SHCreateItemFromParsingName(path,IntPtr.Zero,ref iid,out folder);dialog.SetFolder(folder);}
                }
                int result=dialog.Show(owner==null?IntPtr.Zero:owner.Handle);if(result==unchecked((int)0x800704C7))return null;if(result<0)Marshal.ThrowExceptionForHR(result);
                dialog.GetResult(out item);item.GetDisplayName(0x80058000u,out name);return Marshal.PtrToStringUni(name);
            }finally{
                if(name!=IntPtr.Zero)Marshal.FreeCoTaskMem(name);if(item!=null)Marshal.ReleaseComObject(item);if(folder!=null)Marshal.ReleaseComObject(folder);Marshal.ReleaseComObject(dialog);
            }
        }
    }
    public class MainWindow:Form {
        TextBox folder=new TextBox(),launcher=new TextBox(),log=new TextBox();CheckBox korean=new CheckBox();Button update=new Button(),play=new Button();Label state=new Label();Preferences prefs;string preferenceFile;
        public MainWindow(){
            Text="CTE2 패치기 · "+Engine.Version;AutoScaleMode=AutoScaleMode.Dpi;ClientSize=new Size(760,620);MinimumSize=new Size(776,659);StartPosition=FormStartPosition.CenterScreen;Font=new Font("맑은 고딕",10);BackColor=Color.FromArgb(17,25,39);ForeColor=Color.White;
            Controls.Add(new Label{Text="CTE2 서버 패치",Font=new Font(Font.FontFamily,23,FontStyle.Bold),Location=new Point(24,20),AutoSize=true});Controls.Add(new Label{Text="최신 버전을 확인하고 업데이트한 뒤 게임을 시작하세요.",Location=new Point(27,68),AutoSize=true,ForeColor=Color.LightSteelBlue});
            Controls.Add(new Label{Text="게임 폴더 · 주소창에 %appdata% 입력 가능",Location=new Point(24,110),AutoSize=true});folder.SetBounds(24,135,602,28);Controls.Add(folder);var browse=new Button{Text="폴더 선택",Location=new Point(634,134),Size=new Size(100,30)};browse.Click+=(s,e)=>{try{string selected=ExplorerFolderPicker.Pick(this,folder.Text);if(selected!=null)folder.Text=selected;}catch(Exception ex){MessageBox.Show(this,ex.Message,"폴더 선택",MessageBoxButtons.OK,MessageBoxIcon.Information);}};Controls.Add(browse);
            Controls.Add(new Label{Text="연결할 런처 실행 파일",Location=new Point(24,179),AutoSize=true});launcher.SetBounds(24,204,602,28);Controls.Add(launcher);var choose=new Button{Text="런처 선택",Location=new Point(634,203),Size=new Size(100,30)};choose.Click+=(s,e)=>{using(var d=new OpenFileDialog{Filter="실행 파일 (*.exe)|*.exe",Title="GDLauncher 또는 사용 중인 런처를 선택하세요."})if(d.ShowDialog()==DialogResult.OK)launcher.Text=d.FileName;};Controls.Add(choose);
            Controls.Add(new Label{Text="필수 패치 · 편의 모드 포함",Location=new Point(24,255),AutoSize=true,ForeColor=Color.LightSteelBlue});korean.Text="한국어·한글 리소스팩 자동 설정";korean.SetBounds(264,250,420,30);korean.Checked=true;Controls.Add(korean);
            update.Text="확인하고 업데이트";update.SetBounds(24,294,220,44);update.BackColor=Color.FromArgb(246,196,88);update.ForeColor=Color.FromArgb(20,28,39);update.FlatStyle=FlatStyle.Flat;update.Click+=async(s,e)=>await Run(false);Controls.Add(update);
            play.Text="업데이트 후 런처 실행";play.SetBounds(258,294,280,44);play.Click+=async(s,e)=>await Run(true);Controls.Add(play);var guide=new Button{Text="설치 안내",Location=new Point(552,294),Size=new Size(180,44)};guide.Click+=(s,e)=>Process.Start(Engine.Guide);Controls.Add(guide);
            state.Text="게임을 완전히 종료한 뒤 업데이트하세요. 기존 파일은 백업 후 수정본으로 교체합니다.";state.SetBounds(24,351,710,28);Controls.Add(state);log.SetBounds(24,387,710,200);log.Multiline=true;log.ReadOnly=true;log.ScrollBars=ScrollBars.Vertical;log.BackColor=Color.FromArgb(9,15,25);log.ForeColor=Color.LightSteelBlue;log.Anchor=AnchorStyles.Top|AnchorStyles.Bottom|AnchorStyles.Left|AnchorStyles.Right;Controls.Add(log);
            preferenceFile=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"CTE2-Patcher","preferences.json");try{prefs=Engine.Json.Deserialize<Preferences>(File.ReadAllText(preferenceFile,Encoding.UTF8));folder.Text=prefs.folder;launcher.Text=prefs.launcher;korean.Checked=prefs.korean;}catch{prefs=new Preferences();}
            if(folder.Text.Length==0){string gd=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),"gdlauncher_carbon","data","instances");if(Directory.Exists(gd))folder.Text=gd;}
            foreach(var button in Controls.OfType<Button>()){button.FlatStyle=FlatStyle.Flat;button.UseVisualStyleBackColor=false;if(button!=update){button.BackColor=Color.FromArgb(46,64,84);button.ForeColor=Color.White;}}
            foreach(var box in new[]{folder,launcher}){box.BackColor=Color.FromArgb(28,40,58);box.ForeColor=Color.White;}
            FormClosing+=(s,e)=>{if(!update.Enabled){e.Cancel=true;state.Text="파일 적용 중에는 종료할 수 없습니다. 완료될 때까지 기다려 주세요.";}};
        }
        void Log(string text){if(InvokeRequired){BeginInvoke(new Action<string>(Log),text);return;}log.AppendText(text+Environment.NewLine);}
        void Busy(bool busy){foreach(var button in Controls.OfType<Button>())button.Enabled=!busy;folder.Enabled=launcher.Enabled=korean.Enabled=!busy;}
        async Task Run(bool launch){
            Busy(true);try{
                string root=Engine.NormalizeFolder(folder.Text),role="client";folder.Text=root;
                if(launch&&(!File.Exists(launcher.Text)||!launcher.Text.EndsWith(".exe",StringComparison.OrdinalIgnoreCase)))throw new IOException("사용할 런처 실행 파일을 먼저 지정하세요.");
                state.Text="최신 패치를 확인하고 있습니다…";var latest=await Engine.Latest();Log("최신 패치: "+latest.release_id);Log(latest.notes??"");
                await Engine.Apply(root,latest,role,korean.Checked,Log);state.Text="최신 패치가 적용되었습니다.";
                prefs=new Preferences{folder=root,launcher=launcher.Text,korean=korean.Checked,profile=role};Directory.CreateDirectory(Path.GetDirectoryName(preferenceFile));File.WriteAllText(preferenceFile,Engine.Json.Serialize(prefs),Encoding.UTF8);
                if(launch){state.Text="최신 패치 확인 완료 · 연결된 런처를 실행합니다.";Process.Start(new ProcessStartInfo(launcher.Text){UseShellExecute=true});}
            }catch(Exception e){state.Text="중단됨 · "+e.Message;Log(e.ToString());MessageBox.Show(this,e.Message,"패치를 완료하지 못했습니다",MessageBoxButtons.OK,MessageBoxIcon.Information);}finally{Busy(false);}
        }
    }
    static class Program {
        [STAThread] static void Main(){Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);Application.Run(new MainWindow());}
    }
}
