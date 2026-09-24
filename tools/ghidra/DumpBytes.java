// Dumps raw bytes at addresses as hex, for reading static data tables.
// Headless args: <output file> <address>:<length> [<address>:<length> ...]
// Output is analysis scratch material derived from copyrighted binaries: keep it out of the repository.
//@category WHSHR
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpBytes extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        PrintWriter out = new PrintWriter(new FileWriter(args[0]));
        for (int i = 1; i < args.length; i++) {
            String[] parts = args[i].split(":");
            Address addr = toAddr(parts[0]);
            int len = Integer.parseInt(parts[1]);
            byte[] buf = new byte[len];
            try {
                currentProgram.getMemory().getBytes(addr, buf);
            } catch (Exception e) {
                out.println("# " + parts[0] + " unreadable: " + e);
                continue;
            }
            out.println("# " + parts[0] + " len " + len);
            StringBuilder sb = new StringBuilder();
            for (int j = 0; j < len; j++) {
                sb.append(String.format("%02x", buf[j] & 0xff));
                if ((j & 15) == 15) { out.println(sb); sb = new StringBuilder(); }
            }
            if (sb.length() > 0) out.println(sb);
        }
        out.close();
    }
}
