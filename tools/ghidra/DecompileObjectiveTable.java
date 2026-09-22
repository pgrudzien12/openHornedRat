// Reads the mission-objective record table, creates a Function at each evaluator address if one
// does not already exist, then decompiles all 26 (or fewer, if some entries are null) evaluators
// to one file, headed by the objective letter and the record's flags/caption/a/b snapshot.
// Headless args: <table start address> <record count> <record size> <evaluator field offset> <output file>
// Output is analysis scratch material derived from copyrighted binaries: keep it out of the repository.
//@category WHSHR
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.disassemble.Disassembler;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DecompileObjectiveTable extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Address tableStart = toAddr(args[0]);
        int count = Integer.decode(args[1]);
        int recordSize = Integer.decode(args[2]);
        int evalOffset = Integer.decode(args[3]);
        String outPath = args[4];

        Memory mem = currentProgram.getMemory();
        DecompInterface decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        try (PrintWriter out = new PrintWriter(new FileWriter(outPath))) {
            for (int i = 1; i < count; i++) { // skip index 0 (unused placeholder record)
                if (monitor.isCancelled()) break;
                Address rec = tableStart.add((long) i * recordSize);
                char letter = (char) ('A' + i - 1);
                int flags = mem.getInt(rec.add(0x08));
                int caption = mem.getInt(rec.add(0x0C));
                int evalPtr = mem.getInt(rec.add(evalOffset));
                if (evalPtr == 0) {
                    out.println("// ==== objective " + letter + ": null evaluator pointer");
                    continue;
                }
                Address fnAddr = toAddr(evalPtr & 0xFFFFFFFFL);
                Function f = getFunctionAt(fnAddr);
                if (f == null) {
                    f = getFunctionContaining(fnAddr);
                }
                if (f == null) {
                    // try to disassemble and create a function at this address
                    try {
                        Disassembler disasm = Disassembler.getDisassembler(currentProgram, monitor, null);
                        disasm.disassemble(fnAddr, null);
                        f = createFunction(fnAddr, "eval_" + letter);
                    } catch (Exception e) {
                        out.println("// ==== objective " + letter + " @ " + fnAddr
                                + ": failed to create function: " + e);
                        continue;
                    }
                }
                if (f == null) {
                    out.println("// ==== objective " + letter + " @ " + fnAddr + ": could not create function");
                    continue;
                }
                out.println("// ==== objective " + letter + " @ " + f.getEntryPoint()
                        + " fn=" + f.getName() + " flags=0x" + Integer.toHexString(flags)
                        + " caption=" + caption);
                DecompileResults res = decompiler.decompileFunction(f, 120, monitor);
                out.println(res.decompileCompleted() ? res.getDecompiledFunction().getC()
                        : "// decompilation failed: " + res.getErrorMessage());
                out.println();
            }
        } finally {
            decompiler.dispose();
        }
    }
}
