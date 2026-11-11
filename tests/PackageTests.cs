using System;
using System.IO;
using System.Linq;
using System.Text;
namespace Cte2Patcher {
    public static class PackageTests {
        public static void Main(string[] args){
            try{
                AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling",false);AppContext.SetSwitch("Switch.System.IO.BlockLongPaths",false);
                var release=Engine.Json.Deserialize<Release>(File.ReadAllText(args[0],Encoding.UTF8));string input=Path.GetDirectoryName(Path.GetFullPath(args[0]));
                foreach(string role in new[]{"client","server"}){
                    string root=Path.Combine(Path.GetFullPath(args[1]),role+"-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(Path.Combine(root,"mods"));
                    Engine.InstallBytes(root,release,role,File.ReadAllBytes(Path.Combine(input,"patch-"+role+".zip")),role=="client",s=>{});
                    if(Engine.Needed(root,release.packages[role]).Count!=0)throw new Exception("Full payload integrity mismatch");
                    string stamp=Path.Combine(root,".cte2-patcher","installed.json");if(!File.ReadAllText(stamp).Contains(release.release_id))throw new Exception("Installed release ID mismatch");
                    Console.WriteLine("PASS complete "+role+" payload: "+release.packages[role].files.Count+" real patch files; "+root);
                }
            }catch(Exception ex){Console.WriteLine("FAIL "+ex.GetType().FullName+": "+ex.Message);Environment.ExitCode=1;}
        }
    }
}
