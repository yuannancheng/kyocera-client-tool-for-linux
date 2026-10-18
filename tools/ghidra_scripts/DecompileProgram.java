// Exports decompiled C and structural facts from a Ghidra headless import.
// @category REA

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Iterator;
import java.util.List;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Data;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.listing.Program;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.program.model.symbol.SymbolTable;

public class DecompileProgram extends GhidraScript {
    private static String safeName(String value) {
        return value.replaceAll("[^A-Za-z0-9_.-]", "_");
    }

    private static String esc(String value) {
        return value.replace("\\", "\\\\").replace("\t", "\\t")
                .replace("\r", "\\r").replace("\n", "\\n");
    }

    private void writeCallers(Function function, BufferedWriter out)
            throws IOException {
        ReferenceIterator refs =
                currentProgram.getReferenceManager().getReferencesTo(function.getEntryPoint());
        while (refs.hasNext()) {
            Reference reference = refs.next();
            Address from = reference.getFromAddress();
            Function caller =
                    currentProgram.getFunctionManager().getFunctionContaining(from);
            if (caller != null) {
                out.write(caller.getEntryPoint() + "\t" + esc(caller.getName()) + "\t"
                        + from + "\n");
            }
        }
    }

    private void writeCallees(Function function, BufferedWriter out)
            throws IOException {
        for (Function callee : function.getCalledFunctions(monitor)) {
            out.write(function.getEntryPoint() + "\t" + esc(function.getName()) + "\t"
                    + callee.getEntryPoint() + "\t" + esc(callee.getName()) + "\n");
        }
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "usage: DecompileProgram.java <output-directory>");
        }
        File output = new File(args[0]);
        File codeDir = new File(output, "c");
        if (!codeDir.exists() && !codeDir.mkdirs()) {
            throw new IOException("cannot create " + codeDir);
        }

        Program program = currentProgram;
        FunctionManager functions = program.getFunctionManager();

        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        if (!decompiler.openProgram(program)) {
            throw new IOException("decompiler could not open program");
        }

        List<Function> ordered = new ArrayList<>();
        Iterator<Function> iterator = functions.getFunctions(true);
        while (iterator.hasNext()) {
            ordered.add(iterator.next());
        }
        ordered.sort(Comparator.comparing(Function::getEntryPoint));

        try (BufferedWriter index = new BufferedWriter(
                new FileWriter(new File(output, "functions.tsv")));
                BufferedWriter calls = new BufferedWriter(
                        new FileWriter(new File(output, "calls.tsv")));
                BufferedWriter callers = new BufferedWriter(
                        new FileWriter(new File(output, "callers.tsv")))) {
            index.write("entry\tname\tsize\tparams\tcallers\tcallees\tfile\n");
            calls.write("caller_entry\tcaller\tcallee_entry\tcallee\n");
            callers.write("caller_entry\tcaller\tcall_site\n");

            for (Function function : ordered) {
                String entry = function.getEntryPoint().toString();
                String fileName = "";
                String cText = "";
                String status = "no-body";
                if (function.getBody().getNumAddresses() > 0 && !function.isExternal()) {
                    DecompileResults result =
                            decompiler.decompileFunction(function, 120, monitor);
                    if (result.decompileCompleted()
                            && result.getDecompiledFunction() != null) {
                        cText = result.getDecompiledFunction().getC();
                        status = "ok";
                    } else {
                        status = "decompile-failed: "
                                + result.getErrorMessage().replace('\n', ' ');
                    }
                    if (!cText.isEmpty()) {
                        fileName = safeName(entry + "_" + function.getName()) + ".c";
                        try (BufferedWriter code = new BufferedWriter(
                                new FileWriter(new File(codeDir, fileName)))) {
                            code.write("// entry: " + entry + "\n");
                            code.write("// name: " + function.getName() + "\n");
                            code.write("// signature: " + function.getPrototypeString(false, false)
                                    + "\n");
                            code.write("// body-bytes: "
                                    + function.getBody().getNumAddresses() + "\n\n");
                            code.write(cText);
                        }
                    }
                }
                writeCallees(function, calls);
                writeCallers(function, callers);
                index.write(entry + "\t" + esc(function.getName()) + "\t"
                        + function.getBody().getNumAddresses() + "\t"
                        + function.getParameterCount() + "\t"
                        + function.getCallingFunctions(monitor).size() + "\t"
                        + function.getCalledFunctions(monitor).size() + "\t"
                        + fileName + "\n");
                println(status + " " + entry + " " + function.getName());
            }
        } finally {
            decompiler.dispose();
        }

        try (BufferedWriter strings = new BufferedWriter(
                new FileWriter(new File(output, "strings.tsv")))) {
            strings.write("address\tvalue\n");
            for (Data data : program.getListing().getDefinedData(true)) {
                Object value;
                try {
                    value = data.getValue();
                } catch (Exception ignored) {
                    continue;
                }
                if (data.getValueClass() == String.class && value instanceof String) {
                    strings.write(data.getAddress() + "\t" + esc((String) value) + "\n");
                }
            }
        }

        SymbolTable symbols = program.getSymbolTable();
        try (BufferedWriter imports = new BufferedWriter(
                new FileWriter(new File(output, "symbols.tsv")))) {
            imports.write("address\tname\tnamespace\ttype\n");
            SymbolIterator symbolIterator = symbols.getAllSymbols(true);
            while (symbolIterator.hasNext()) {
                Symbol symbol = symbolIterator.next();
                imports.write(symbol.getAddress() + "\t" + esc(symbol.getName()) + "\t"
                        + esc(symbol.getParentNamespace().getName()) + "\t"
                        + symbol.getSymbolType() + "\n");
            }
        }
    }
}
