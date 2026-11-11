using System;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Collections.Generic;
using System.Text;

namespace Cte2Patcher {
    public static class EngineTests {
        static byte[] Bytes(string s){return Encoding.UTF8.GetBytes(s);}
        static void Check(bool b,string message){if(!b)throw new Exception(message);}
        static void Rejected(Action action){try{action();}catch(InvalidDataException){return;}catch(IOException){return;}catch(ArgumentException){return;}catch(UnauthorizedAccessException){return;}throw new Exception("Unsafe operation was admitted");}
        static Release Make(Dictionary<string,string> files,out byte[] archive){
            var entries=new List<PatchFile>();using(var memory=new MemoryStream()){
                using(var zip=new ZipArchive(memory,ZipArchiveMode.Create,true))foreach(var e in files){var b=Bytes(e.Value);using(var stream=zip.CreateEntry(e.Key).Open())stream.Write(b,0,b.Length);entries.Add(new PatchFile{path=e.Key,bytes=b.Length,sha256=Engine.Hash(b)});}
                archive=memory.ToArray();
            }
            var p=new Package{url="https://github.com/piro0101/CTE2-Multi/releases/download/test/patch-client.zip",bytes=archive.Length,sha256=Engine.Hash(archive),files=entries};
            return new Release{schema=1,release_id="test-1",minimum_patcher="1.0.0",packages=new Dictionary<string,Package>{{"client",p},{"server",p}}};
        }
        static void Put(string root,string path,string text){string p=Path.Combine(root,path);Directory.CreateDirectory(Path.GetDirectoryName(p));File.WriteAllText(p,text,new UTF8Encoding(false));}
        static string Read(string root,string path){return File.ReadAllText(Path.Combine(root,path),Encoding.UTF8);}
        public static void Main(string[] args){
            try{Run(args);}catch(Exception ex){Console.WriteLine("FAIL "+ex.GetType().FullName+": "+ex.Message);Environment.ExitCode=1;}
        }
        static void Run(string[] args){
            AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling",false);AppContext.SetSwitch("Switch.System.IO.BlockLongPaths",false);
            string root=Path.GetFullPath(args[0]);Directory.CreateDirectory(root);root=Path.Combine(root,Guid.NewGuid().ToString("N"));Directory.CreateDirectory(root);
            foreach(string path in new[]{"../outside.txt","mods/../../escape","/mods/a.jar","C:/Windows/a","mods\\a.jar","saves/world/level.dat","mods/CON.jar","mods/a.jar.","mods/a.jar:stream"})Rejected(()=>Engine.Child(root,path));
            Put(root,"mods/addon.jar","old");Put(root,"options.txt","music:0.4\nresourcePacks:[\"vanilla\",\"file/my-pack.zip\"]\nlang:en_us\n");Put(root,"saves/local/level.dat","private world");Put(root,"servers.dat","private server list");
            byte[] archive;var release=Make(new Dictionary<string,string>{{"mods/addon.jar","new"},{"config/test.json","{}"}},out archive);Engine.Validate(release);
            byte[] damaged=(byte[])archive.Clone();damaged[damaged.Length-1]^=1;Rejected(()=>Engine.InstallBytes(root,release,"client",damaged,true,s=>{}));Check(Read(root,"mods/addon.jar")=="old","Corruption must not mutate target");
            using(var held=new FileStream(Path.Combine(root,"mods/addon.jar"),FileMode.Open,FileAccess.Read,FileShare.Read))Rejected(()=>Engine.InstallBytes(root,release,"client",archive,true,s=>{}));Check(Read(root,"mods/addon.jar")=="old","In-use archive must not be overwritten");
            Engine.InstallBytes(root,release,"client",archive,true,s=>{});Check(Read(root,"mods/addon.jar")=="new"&&Engine.Needed(root,release.packages["client"]).Count==0,"Files installed and verified");
            var options=Read(root,"options.txt");Check(options.Contains("music:0.4")&&options.Contains("file/my-pack.zip")&&options.Contains("lang:ko_kr"),"Preserve user choices and activate Korean");Check(Engine.KoreanOptions(Bytes(options)).SequenceEqual(Bytes(options)),"Resource pack activation is idempotent");Check(Read(root,"saves/local/level.dat")=="private world"&&Read(root,"servers.dat")=="private server list","World and server list must be untouched");
            Put(root,"mods/addon.jar","old");Put(root,"config/test.json","old config");File.SetAttributes(Path.Combine(root,"config/test.json"),FileAttributes.ReadOnly);
            try{Rejected(()=>Engine.InstallBytes(root,release,"server",archive,false,s=>{}));Check(Read(root,"mods/addon.jar")=="old"&&Read(root,"config/test.json")=="old config","Mid-apply failure restores all originals");}finally{File.SetAttributes(Path.Combine(root,"config/test.json"),FileAttributes.Normal);}
            string oldAdv="config/openloader/data/cte_configuration/data/cte2/advancements/bounty_hunting/novice_miner.json";Put(root,oldAdv,"old advancement");Engine.InstallBytes(root,release,"server",archive,false,s=>{});Check(!File.Exists(Path.Combine(root,oldAdv)),"Enabled old advancement quarantined");Check(Directory.GetFiles(@"\\?\"+Path.Combine(root,".cte2-patcher","backups"),"novice_miner.json",SearchOption.AllDirectories).Length>=1,"Quarantined file retained");
            var invalid=Make(new Dictionary<string,string>{{"mods/a.jar","a"}},out damaged);invalid.minimum_patcher="999.0.0";Rejected(()=>Engine.Validate(invalid));
            string area=Path.Combine(root,".cte2-patcher");Put(root,"config/recovery.txt","new");Put(area,"backups/resume/config/recovery.txt","before");var journal=new Journal{root=root,backup="backups/resume",phase="applying",changes=new List<Change>{new Change{path="config/recovery.txt",existed=true,before=Engine.Hash(Bytes("before")),after=Engine.Hash(Bytes("new")),staged="unused"}}};Put(area,"pending.json",Engine.Json.Serialize(journal));Engine.Recover(root,s=>{});Check(Read(root,"config/recovery.txt")=="before","Interrupted transaction recovery");
            Console.WriteLine("PASS paths/ZIP traversal, corrupt package refusal, in-use JAR lock, install/hash validation, preserved worlds/server list, Korean options, rollback, quarantine, pending recovery and minimum patcher version. Test evidence: "+root);
        }
    }
}
