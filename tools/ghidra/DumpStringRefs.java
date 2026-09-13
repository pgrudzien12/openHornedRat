// Lists defined strings matching a regex and every reference to them (code or pointer tables).
// For a pointer slot without direct references, the nearest referenced address up to 512 bytes
// before it is reported as the probable table start.
// Headless args: <regex> <output file>
//@category WHSHR
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.DataIterator;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.HashSet;
import java.util.Set;
import java.util.regex.Pattern;

public class DumpStringRefs extends GhidraScript {
    private ReferenceManager refs;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Pattern pattern = Pattern.compile(args[0]);
        refs = currentProgram.getReferenceManager();
        try (PrintWriter out = new PrintWriter(new FileWriter(args[1]))) {
            DataIterator it = currentProgram.getListing().getDefinedData(true);
            while (it.hasNext() && !monitor.isCancelled()) {
                Data d = it.next();
                if (!d.hasStringValue() || d.getValue() == null) {
                    continue;
                }
                String s = d.getValue().toString();
                if (!pattern.matcher(s).find()) {
                    continue;
                }
                out.println("STR " + d.getAddress() + " " + s);
                dump(out, d.getAddress(), 1, new HashSet<>());
            }
        }
    }

    private void dump(PrintWriter out, Address target, int depth, Set<Address> seen) {
        if (depth > 3 || !seen.add(target)) {
            return;
        }
        String indent = "  ".repeat(depth);
        for (Reference r : refs.getReferencesTo(target)) {
            Address from = r.getFromAddress();
            Function f = getFunctionContaining(from);
            if (f != null) {
                out.println(indent + r.getReferenceType() + " from " + from + " in " + f.getName() + "@" + f.getEntryPoint());
                continue;
            }
            out.println(indent + r.getReferenceType() + " from data " + from);
            if (refs.getReferenceCountTo(from) > 0) {
                dump(out, from, depth + 1, seen);
                continue;
            }
            for (int back = 1; back <= 512; back++) {
                Address a = from.subtractWrap(back);
                if (refs.getReferenceCountTo(a) > 0) {
                    out.println(indent + "  table start " + a + " (slot offset " + back + ")");
                    dump(out, a, depth + 1, seen);
                    break;
                }
            }
        }
    }
}
