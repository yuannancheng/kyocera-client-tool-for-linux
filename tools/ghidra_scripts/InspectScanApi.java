// Exports the KM-WSDL scan API surface and functions that use its protocol
// strings or networking APIs. Intended for focused analysis of KMSCNAPI.dll.
// @category REA

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

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

public class InspectScanApi extends GhidraScript {
    private static final String[] NETWORK_API_PARTS = {
        "internet", "http", "socket", "connect", "send", "receive", "recv",
        "wsa"
    };

    private static final String[] PROTOCOL_STRING_PARTS = {
        "http://", "https://", "soap", "km-wsdl", "scan_operation",
        "open_session", "start_scan", "retrieve_image", "cancel_scan",
        "close_session", "get_capability", "get_default_configuration",
        "get_service_information", "kmscn", "content-type", "soapaction",
        ":9090/", ":9091/", "kmnet", "auth", "login", "logout",
        "scanneraddress", "kmw"
    };

    private static String safeName(String value) {
        return value.replaceAll("[^A-Za-z0-9_.-]", "_");
    }

    private static String esc(String value) {
        return value.replace("\\", "\\\\").replace("\t", "\\t")
                .replace("\r", "\\r").replace("\n", "\\n");
    }

    private static boolean containsAny(String value, String[] parts) {
        String lower = value.toLowerCase(Locale.ROOT);
        for (String part : parts) {
            if (lower.contains(part)) {
                return true;
            }
        }
        return false;
    }

    private static void addReason(Map<Address, String> selected,
            Function function, String reason) {
        if (function == null || function.isExternal()
                || function.getBody().getNumAddresses() == 0) {
            return;
        }
        selected.putIfAbsent(function.getEntryPoint(), reason);
    }

    private static void addReferencingFunctions(Program program,
            Address address, String reason, Map<Address, String> selected) {
        ReferenceIterator refs =
                program.getReferenceManager().getReferencesTo(address);
        while (refs.hasNext()) {
            Reference ref = refs.next();
            Function caller = program.getFunctionManager()
                    .getFunctionContaining(ref.getFromAddress());
            addReason(selected, caller,
                    reason + " via " + ref.getFromAddress());
        }
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "usage: InspectScanApi.java <output-directory>");
        }

        File output = new File(args[0]);
        File codeDir = new File(output, "c");
        if (!codeDir.exists() && !codeDir.mkdirs()) {
            throw new IOException("cannot create " + codeDir);
        }

        Program program = currentProgram;
        FunctionManager functions = program.getFunctionManager();
        Map<Address, String> selected = new LinkedHashMap<>();

        FunctionIterator functionIterator = functions.getFunctions(true);
        while (functionIterator.hasNext()) {
            Function function = functionIterator.next();
            String name = function.getName();
            if (!function.isExternal() && (name.startsWith("KMSCN")
                    || name.equals("openSessionReqInit")
                    || name.equals("startScanReqInit"))) {
                selected.put(function.getEntryPoint(), "scan export");
            }
        }

        FunctionIterator allFunctions = functions.getFunctions(true);
        while (allFunctions.hasNext()) {
            Function function = allFunctions.next();
            if (function.isExternal()
                    && containsAny(function.getName(), NETWORK_API_PARTS)) {
                addReferencingFunctions(program, function.getEntryPoint(),
                        "network API " + function.getName(), selected);
            }
        }

        try (BufferedWriter strings = new BufferedWriter(
                new FileWriter(new File(output, "protocol-strings.tsv")));
                BufferedWriter xrefs = new BufferedWriter(
                        new FileWriter(new File(output, "protocol-xrefs.tsv")))) {
            strings.write("address\tvalue\n");
            xrefs.write("string_address\tfrom_address\tfunction_entry\tfunction\tvalue\n");

            for (Data data : program.getListing().getDefinedData(true)) {
                Object value;
                try {
                    value = data.getValue();
                } catch (Exception ignored) {
                    continue;
                }
                if (data.getValueClass() != String.class
                        || !(value instanceof String)) {
                    continue;
                }
                String text = (String) value;
                if (!containsAny(text, PROTOCOL_STRING_PARTS)) {
                    continue;
                }
                strings.write(data.getAddress() + "\t" + esc(text) + "\n");

                ReferenceIterator refs =
                        program.getReferenceManager().getReferencesTo(
                                data.getAddress());
                while (refs.hasNext()) {
                    Reference ref = refs.next();
                    Function caller = functions.getFunctionContaining(
                            ref.getFromAddress());
                    String callerEntry = caller == null
                            ? "" : caller.getEntryPoint().toString();
                    String callerName = caller == null ? "" : caller.getName();
                    xrefs.write(data.getAddress() + "\t" + ref.getFromAddress()
                            + "\t" + callerEntry + "\t" + esc(callerName)
                            + "\t" + esc(text) + "\n");
                    addReason(selected, caller,
                            "protocol string " + data.getAddress());
                }
            }
        }

        DecompInterface decompiler = new DecompInterface();
        decompiler.toggleCCode(true);
        decompiler.toggleSyntaxTree(true);
        if (!decompiler.openProgram(program)) {
            throw new IOException("decompiler could not open program");
        }

        List<Address> ordered = new ArrayList<>(selected.keySet());
        ordered.sort(Comparator.naturalOrder());
        try (BufferedWriter index = new BufferedWriter(
                new FileWriter(new File(output, "selected-functions.tsv")))) {
            index.write("entry\tname\tsize\treason\tfile\n");
            for (Address entry : ordered) {
                Function function =
                        functions.getFunctionContaining(entry);
                if (function == null || function.isExternal()
                        || function.getBody().getNumAddresses() == 0) {
                    continue;
                }
                String fileName = safeName(entry + "_"
                        + function.getName()) + ".c";
                DecompileResults result =
                        decompiler.decompileFunction(function, 120, monitor);
                if (result.decompileCompleted()
                        && result.getDecompiledFunction() != null) {
                    try (BufferedWriter code = new BufferedWriter(
                            new FileWriter(new File(codeDir, fileName)))) {
                        code.write("// entry: " + entry + "\n");
                        code.write("// name: " + function.getName() + "\n");
                        code.write("// signature: "
                                + function.getPrototypeString(false, false)
                                + "\n");
                        code.write("// body-bytes: "
                                + function.getBody().getNumAddresses() + "\n");
                        code.write("// selection: " + selected.get(entry) + "\n\n");
                        code.write(result.getDecompiledFunction().getC());
                    }
                } else {
                    fileName = "";
                    println("decompile-failed " + entry + " "
                            + result.getErrorMessage());
                }
                index.write(entry + "\t" + esc(function.getName()) + "\t"
                        + function.getBody().getNumAddresses() + "\t"
                        + esc(selected.get(entry)) + "\t" + fileName + "\n");
            }
        } finally {
            decompiler.dispose();
        }
    }
}
