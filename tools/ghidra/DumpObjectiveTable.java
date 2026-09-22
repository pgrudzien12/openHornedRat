// Dumps the mission-objective record table (26 x 40-byte records starting at a given address):
// per record, the evaluator function pointer field and its offset, resolved to a function name/address.
// Headless args: <table start address> <record count> <record size> <evaluator field offset> <output file>
// Output is analysis scratch material derived from copyrighted binaries: keep it out of the repository.
//@category WHSHR
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpObjectiveTable extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Address tableStart = toAddr(args[0]);
        int count = Integer.decode(args[1]);
        int recordSize = Integer.decode(args[2]);
        int evalOffset = Integer.decode(args[3]);
        String outPath = args[4];

        Memory mem = currentProgram.getMemory();
        try (PrintWriter out = new PrintWriter(new FileWriter(outPath))) {
            out.println("index letter record_addr flags_u32 caption_u32 evaluator_addr evaluator_fn met_u32 a_i32 b_i32");
            for (int i = 0; i < count; i++) {
                Address rec = tableStart.add((long) i * recordSize);
                char letter = (char) ('A' + i - 1); // index 0 unused, 1='A'
                int defined = mem.getInt(rec);
                int flags = mem.getInt(rec.add(0x08));
                int caption = mem.getInt(rec.add(0x0C));
                int evalPtr = mem.getInt(rec.add(evalOffset));
                int met = mem.getInt(rec.add(0x14));
                int a = mem.getInt(rec.add(0x18));
                int b = mem.getInt(rec.add(0x1C));
                String fnName = "?";
                if (evalPtr != 0) {
                    Address fnAddr = toAddr(evalPtr & 0xFFFFFFFFL);
                    Function f = getFunctionAt(fnAddr);
                    if (f == null) f = getFunctionContaining(fnAddr);
                    fnName = (f != null) ? f.getName() : "NO_FUNC";
                }
                out.printf("%d %s %s defined=%d flags=0x%x caption=%d eval=0x%x(%s) met=%d a=%d b=%d%n",
                        i, (i >= 1 && i <= 26) ? String.valueOf(letter) : "-", rec,
                        defined, flags, caption, evalPtr, fnName, met, a, b);
            }
        }
    }
}
