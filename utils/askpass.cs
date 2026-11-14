using System;
using System.Collections;

class AskPass {
    static int Main(string[] args) {
        string prompt = args.Length > 0 ? args[0] : "";
        string promptLower = prompt.ToLowerInvariant();
        
        string token = null;
        string user = null;
        
        foreach (DictionaryEntry de in Environment.GetEnvironmentVariables()) {
            string key = de.Key as string;
            if (key == null) continue;
            if (key.StartsWith("AUTOGIT_ASKPASS_TOKEN")) {
                token = de.Value as string;
            } else if (key.StartsWith("AUTOGIT_ASKPASS_USER")) {
                user = de.Value as string;
            }
        }
        
        if (string.IsNullOrEmpty(user)) {
            user = "x-access-token";
        }
        
        int userIdx = promptLower.IndexOf("username", StringComparison.Ordinal);
        int passIdx = promptLower.IndexOf("password", StringComparison.Ordinal);
        
        if (passIdx >= 0 && (userIdx < 0 || passIdx <= userIdx)) {
            Console.WriteLine(token ?? "");
        } else if (userIdx >= 0) {
            Console.WriteLine(user);
        } else {
            Console.WriteLine("");
        }
        return 0;
    }
}

