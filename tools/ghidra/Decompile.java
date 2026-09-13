// Decompiles functions to a text file, with their callers.
// Headless args: <output file> all | <address> [<address> ...]
// Output is analysis scratch material derived from copyrighted binaries: keep it out of the repository.
//@category WHSHR
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

public class Decompile extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        List<Function> functions = new ArrayList<>();
        if (args.length == 2 && args[1].equals("all")) {
            FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
            while (it.hasNext()) {
                functions.add(it.next());
            }
        } else {
            for (int i = 1; i < args.length; i++) {
                Function f = getFunctionContaining(toAddr(args[i]));
                if (f == null) {
                    println("no function at " + args[i]);
                } else {
                    functions.add(f);
                }
            }
        }
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);
        try (PrintWriter out = new PrintWriter(new FileWriter(args[0]))) {
            for (Function f : functions) {
                if (monitor.isCancelled()) {
                    break;
                }
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
