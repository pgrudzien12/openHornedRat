// Like Decompile.java but creates a Function at each address first if one doesn't already exist
// (for code reached only via a data pointer table, which auto-analysis may not have found).
// Headless args: <output file> <address> [<address> ...]
// Output is analysis scratch material derived from copyrighted binaries: keep it out of the repository.
//@category WHSHR
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.disassemble.Disassembler;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

public class DecompileCreate extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        List<Function> functions = new ArrayList<>();
        for (int i = 1; i < args.length; i++) {
            Address addr = toAddr(args[i]);
            Function f = getFunctionAt(addr);
            if (f == null) f = getFunctionContaining(addr);
            if (f == null) {
                try {
                    Disassembler disasm = Disassembler.getDisassembler(currentProgram, monitor, null);
                    disasm.disassemble(addr, null);
                    f = createFunction(addr, "fn_" + addr);
                } catch (Exception e) {
                    println("failed to create function at " + args[i] + ": " + e);
                }
            }
            if (f == null) {
                println("no function at " + args[i]);
            } else {
                functions.add(f);
            }
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (Function f : functions) {
                if (monitor.isCancelled()) break;
                StringBuilder callers = new StringBuilder();
                for (Function c : f.getCallingFunctions(monitor)) {
                    callers.append(' ').append(c.getEntryPoint());
                }
                out.println("// ==== " + f.getName() + " @ " + f.getEntryPoint() + " callers:" + callers);
                DecompileResults res = decompiler.decompileFunction(f, 120, monitor);
                out.println(res.decompileCompleted() ? res.getDecompiledFunction().getC()
                        : "// decompilation failed: " + res.getErrorMessage());
            }
        } finally {
            decompiler.dispose();
        }
    }
}
