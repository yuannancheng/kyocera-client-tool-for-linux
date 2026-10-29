// Decompile the functions containing explicitly selected addresses.
// Intended for focused follow-up analysis without rerunning a full export.
// @category REA

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;

public class DecompileAddresses extends GhidraScript {
    private static String safeName(String value) {
        return value.replaceAll("[^A-Za-z0-9_.-]", "_");
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 2) {
            throw new IllegalArgumentException(
                    "usage: DecompileAddresses.java <output-directory> <address>...");
        }

        File output = new File(args[0]);
        if (!output.exists() && !output.mkdirs()) {
            throw new IOException("cannot create " + output);
        }

        FunctionManager functions = currentProgram.getFunctionManager();
        Map<Address, String> selected = new LinkedHashMap<>();
        List<String> unresolved = new ArrayList<>();
        for (int index = 1; index < args.length; index++) {
            Address address = toAddr(args[index]);
            Function function = functions.getFunctionContaining(address);
            if (function == null) {
                unresolved.add(args[index]);
                continue;
            }
            selected.putIfAbsent(function.getEntryPoint(), args[index]);
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        if (!decompiler.openProgram(currentProgram)) {
            throw new IOException("decompiler could not open program");
        }

        List<Address> ordered = new ArrayList<>(selected.keySet());
        ordered.sort(Address::compareTo);
        try (BufferedWriter index = new BufferedWriter(
                new FileWriter(new File(output, "index.tsv")))) {
            index.write("entry\tname\tsize\trequested_addresses\tfile\n");
            for (String address : unresolved) {
                index.write("\tunresolved\t0\t" + address + "\t\n");
            }
            for (Address entry : ordered) {
                Function function = functions.getFunctionAt(entry);
                if (function == null || function.isExternal()) {
                    continue;
                }
                String fileName = safeName(entry + "_" + function.getName()) + ".c";
                DecompileResults result =
                        decompiler.decompileFunction(function, 120, monitor);
                if (!result.decompileCompleted()
                        || result.getDecompiledFunction() == null) {
                    index.write(entry + "\t" + function.getName() + "\t"
                            + function.getBody().getNumAddresses() + "\t"
                            + selected.get(entry) + "\tdecompile-failed\n");
                    continue;
                }
                try (BufferedWriter code = new BufferedWriter(
                        new FileWriter(new File(output, fileName)))) {
                    code.write("// entry: " + entry + "\n");
                    code.write("// name: " + function.getName() + "\n");
                    code.write("// signature: "
                            + function.getPrototypeString(false, false) + "\n");
                    code.write("// body-bytes: "
                            + function.getBody().getNumAddresses() + "\n");
                    code.write("// requested-address: "
                            + selected.get(entry) + "\n\n");
                    code.write(result.getDecompiledFunction().getC());
                }
                index.write(entry + "\t" + function.getName() + "\t"
                        + function.getBody().getNumAddresses() + "\t"
                        + selected.get(entry) + "\t" + fileName + "\n");
            }
        } finally {
            decompiler.dispose();
        }
    }
}
