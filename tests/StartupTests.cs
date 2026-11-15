using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

namespace Cte2Patcher {
    public static class StartupTests {
        [STAThread] public static void Main(string[] args){
            // Do not set path switches or use System.IO before the real app entry.
            // This reproduces startup through Forms, which previously cached legacy IO.
            bool ran=false;
            Application.Idle+=(sender,eventArgs)=>{
                if(ran||Application.OpenForms.Count==0)return;ran=true;
                var window=Application.OpenForms[0];window.Hide();
                try{
                    var release=Engine.Json.Deserialize<Release>(File.ReadAllText(args[0],Encoding.UTF8));
                    string input=Path.GetDirectoryName(Path.GetFullPath(args[0]));
                    foreach(string role in new[]{"client","server"}){
                        string root=Path.Combine(Path.GetFullPath(args[1]),"한글 게임 폴더 "+role+"-"+Guid.NewGuid().ToString("N"));
                        Directory.CreateDirectory(Path.Combine(root,"mods"));
                        File.WriteAllText(Path.Combine(root,"mods","Mine_and_Slash-1.20.1-6.4.13.jar"),"ISOLATED TEST MARKER");
                        File.WriteAllText(Path.Combine(root,"options.txt"),"resourcePacks:[\"vanilla\"]\nlang:en_us\n");
                        if(!release.packages[role].files.Any(f=>Path.Combine(root,".cte2-patcher","backups","20261115-000000-12345678",f.path).Length>260))throw new Exception("Fixture must exceed MAX_PATH");
                        Engine.InstallBytes(root,release,role,File.ReadAllBytes(Path.Combine(input,"patch-"+role+".zip")),role=="client",s=>{});
                        if(Engine.Needed(root,release.packages[role]).Count!=0)throw new Exception("Installed bytes mismatch");
                        Console.WriteLine("PASS actual GUI entry startup + long Korean path + "+role+" install "+release.packages[role].files.Count+" files");
                    }
                }catch(Exception ex){Console.WriteLine("FAIL actual GUI startup: "+ex);Environment.ExitCode=1;}
                finally{window.Close();}
            };
            typeof(Engine).Assembly.GetType("Cte2Patcher.Program").GetMethod("Main",BindingFlags.Static|BindingFlags.NonPublic).Invoke(null,null);
            if(!ran){Console.WriteLine("FAIL actual entry did not reach GUI");Environment.ExitCode=1;}
        }
    }
}
