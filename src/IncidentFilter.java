import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;


public class IncidentFilter {

    // ---------- Allowed incident types ----------
    enum IncidentType {
        EARTHQUAKE, FLOOD, BOMBING, TORNADO, FIRE, OTHER;

        static IncidentType fromFreeText(String s) {
            if (s == null) return OTHER;
            String t = s.toLowerCase(Locale.ROOT);

            // Map common variants to the required buckets
            if (containsAny(t, "earthquake", "seismic", "tremor", "quake")) return EARTHQUAKE;
            if (containsAny(t, "flood", "flash flood", "inundat", "overflow")) return FLOOD;
            if (containsAny(t, "bomb", "bombing", "blast", "explosion", "explosive", "detonation")) return BOMBING;
            if (containsAny(t, "tornado", "twister", "funnel")) return TORNADO;
            if (containsAny(t, "fire", "wildfire", "burn", "blaze")) return FIRE;

            return OTHER;
        }

        static IncidentType fromCliType(String s) {
            if (s == null) return null;
            String t = s.trim().toLowerCase(Locale.ROOT);
            switch (t) {
                case "earthquake": return EARTHQUAKE;
                case "flood": return FLOOD;
                case "bombing": return BOMBING;
                case "tornado": return TORNADO;
                case "fire": return FIRE;
                case "other": return OTHER;
                default:
                    throw new IllegalArgumentException("--type must be one of: earthquake, flood, bombing, tornado, fire, other");
            }
        }

        static boolean containsAny(String haystack, String... needles) {
            for (String n : needles) if (haystack.contains(n)) return true;
            return false;
        }
    }

    // ---------- Data model ----------
    static class Incident {
        int observerId = -1;
        String targetedLocation = "";
        String currentLocation = "";
        String incidentTypeRaw = "";
        IncidentType incidentTypeNorm = IncidentType.OTHER;

        String time = "";
        String text = "";
        String immediacy = "";

        Double severity = null; // PROVIDED BY FILE (not computed)

        /** We treat "location" as targeted first; if missing, fallback to current. */
        String primaryLocation() {
            String t = safe(targetedLocation).trim();
            if (!t.isEmpty()) return t;
            return safe(currentLocation).trim();
        }

        String primaryLocationKey() {
            return normalizeLocationKey(primaryLocation());
        }
    }

    // ---------- Parsing (Observer blocks) ----------
    private static final Pattern OBSERVER_HEADER = Pattern.compile("^\\s*Observer\\s+(\\d+)\\s*:\\s*$");
    private static final Pattern KV = Pattern.compile("^\\s*([^:]+?)\\s*:\\s*(.*)\\s*$");

    static List<Incident> parseObservers(List<String> lines) {
        List<Incident> out = new ArrayList<>();
        Incident cur = null;

        for (String raw : lines) {
            String line = raw.stripTrailing();

            Matcher h = OBSERVER_HEADER.matcher(line);
            if (h.matches()) {
                if (cur != null) out.add(cur);
                cur = new Incident();
                cur.observerId = Integer.parseInt(h.group(1));
                continue;
            }

            if (cur == null) continue;

            Matcher m = KV.matcher(line);
            if (!m.matches()) continue;

            String k = m.group(1).trim();
            String v = stripOuterQuotes(m.group(2).trim());

            String kl = k.toLowerCase(Locale.ROOT);

            switch (kl) {
                case "location 1 (targeted)":
                    cur.targetedLocation = v;
                    break;
                case "location 2 (current)":
                    cur.currentLocation = v;
                    break;
                case "incident type":
                    cur.incidentTypeRaw = v;
                    cur.incidentTypeNorm = IncidentType.fromFreeText(v);
                    break;
                case "time":
                    cur.time = v;
                    break;
                case "text":
                    cur.text = v;
                    break;
                case "immediacy of action":
                    cur.immediacy = v;
                    break;
                default:
                    if (isSeverityKey(kl)) {
                        cur.severity = tryParseDouble(v);
                    }
                    break;
            }
        }

        if (cur != null) out.add(cur);
        return out;
    }

    static boolean isSeverityKey(String kl) {
        kl = kl.replaceAll("[\\s_\\-]", "");
        return kl.equals("severity") || kl.equals("severityscore") || kl.equals("severitylevel") || kl.equals("severityscorevalue");
    }

    static Double tryParseDouble(String s) {
        if (s == null) return null;
        Matcher m = Pattern.compile("(-?\\d+(?:\\.\\d+)?)").matcher(s);
        if (!m.find()) return null;
        try {
            return Double.parseDouble(m.group(1));
        } catch (Exception e) {
            return null;
        }
    }

    // ---------- Filtering ----------
    static boolean matchesFilters(Incident i, String locationSubstr, IncidentType typeFilter) {
        boolean ok = true;

        if (locationSubstr != null && !locationSubstr.isBlank()) {
            String needle = locationSubstr.toLowerCase(Locale.ROOT);

            ok &= safe(i.targetedLocation).toLowerCase(Locale.ROOT).contains(needle)
               || safe(i.currentLocation).toLowerCase(Locale.ROOT).contains(needle);
        }

        if (typeFilter != null) {
            ok &= (i.incidentTypeNorm == typeFilter);
        }

        return ok;
    }

    // ---------- Hotspot counting ----------
    static Map<String, Integer> buildLocationCounts(List<Incident> incidents) {
        Map<String, Integer> counts = new HashMap<>();
        for (Incident i : incidents) {
            String key = i.primaryLocationKey();
            if (key.isEmpty()) key = "(unknown)";
            counts.put(key, counts.getOrDefault(key, 0) + 1);
        }
        return counts;
    }

    // ---------- Output ----------
    static void writeCsv(List<Incident> incidents, Map<String, Integer> locationCounts, Path out) throws IOException {
        try (BufferedWriter w = Files.newBufferedWriter(out, StandardCharsets.UTF_8)) {
            w.write("observer_id,location,location_incident_count,incident_type,severity,time,text,immediacy");
            w.newLine();
            for (Incident i : incidents) {
                String loc = i.primaryLocation();
                String key = i.primaryLocationKey();
                int cnt = locationCounts.getOrDefault(key.isEmpty() ? "(unknown)" : key, 0);

                w.write(Integer.toString(i.observerId));
                w.write(",");
                w.write(csv(loc));
                w.write(",");
                w.write(Integer.toString(cnt));
                w.write(",");
                w.write(csv(i.incidentTypeNorm.name()));
                w.write(",");
                w.write(csv(i.severity == null ? "" : String.format(Locale.ROOT, "%.4f", i.severity)));
                w.write(",");
                w.write(csv(i.time));
                w.write(",");
                w.write(csv(i.text));
                w.write(",");
                w.write(csv(i.immediacy));
                w.newLine();
            }
        }
    }

    static void writeJson(List<Incident> incidents, Map<String, Integer> locationCounts, Path out) throws IOException {
        try (BufferedWriter w = Files.newBufferedWriter(out, StandardCharsets.UTF_8)) {
            w.write("[\n");
            for (int idx = 0; idx < incidents.size(); idx++) {
                Incident i = incidents.get(idx);
                String loc = i.primaryLocation();
                String key = i.primaryLocationKey();
                int cnt = locationCounts.getOrDefault(key.isEmpty() ? "(unknown)" : key, 0);

                w.write("  {\n");
                w.write("    \"observer_id\": " + i.observerId + ",\n");
                w.write("    \"location\": " + json(loc) + ",\n");
                w.write("    \"location_incident_count\": " + cnt + ",\n");
                w.write("    \"incident_type\": " + json(i.incidentTypeNorm.name()) + ",\n");
                w.write("    \"severity\": " + (i.severity == null ? "null" : String.format(Locale.ROOT, "%.4f", i.severity)) + ",\n");
                w.write("    \"time\": " + json(i.time) + ",\n");
                w.write("    \"text\": " + json(i.text) + ",\n");
                w.write("    \"immediacy\": " + json(i.immediacy) + "\n");
                w.write("  }" + (idx == incidents.size() - 1 ? "\n" : ",\n"));
            }
            w.write("]\n");
        }
    }

    // ---------- CLI ----------
    static class Args {
        String inPath = null;
        String outPath = "filtered_sorted.csv";
        String format = "csv"; // csv|json
        String location = null;
        IncidentType type = null;
    }

    static Args parseArgs(String[] args) {
        Args a = new Args();
        for (int i = 0; i < args.length; i++) {
            String cur = args[i];
            switch (cur) {
                case "--in":
                    a.inPath = nextArg(args, ++i, "--in requires a filepath");
                    break;
                case "--out":
                    a.outPath = nextArg(args, ++i, "--out requires a filepath");
                    break;
                case "--format":
                    a.format = nextArg(args, ++i, "--format requires csv or json").toLowerCase(Locale.ROOT);
                    break;
                case "--location":
                    a.location = nextArg(args, ++i, "--location requires text");
                    break;
                case "--type":
                    a.type = IncidentType.fromCliType(nextArg(args, ++i, "--type requires a value"));
                    break;
                case "--help":
                case "-h":
                    printHelpAndExit();
                    break;
                default:
                    throw new IllegalArgumentException("Unknown arg: " + cur + " (use --help)");
            }
        }
        if (a.inPath == null) throw new IllegalArgumentException("Missing --in <file path>. Use --help.");
        if (!a.format.equals("csv") && !a.format.equals("json")) {
            throw new IllegalArgumentException("--format must be csv or json");
        }
        return a;
    }

    static String nextArg(String[] args, int i, String err) {
        if (i >= args.length) throw new IllegalArgumentException(err);
        return args[i];
    }

    static void printHelpAndExit() {
        System.out.println(
            "IncidentFilter (hotspot severity via location count; no severity computation)\n" +
            "  --in <path>         Input text file\n" +
            "  --out <path>        Output file (default: filtered_sorted.csv)\n" +
            "  --format csv|json   Output format (default: csv)\n" +
            "  --location <text>   Filter by location substring (targeted OR current)\n" +
            "  --type <t>          Filter by type: earthquake|flood|bombing|tornado|fire|other\n"
        );
        System.exit(0);
    }

    // ---------- Helpers ----------
    static String safe(String s) { return s == null ? "" : s; }

    /** Normalizes a location for grouping: lowercase, trim, collapse spaces. */
    static String normalizeLocationKey(String loc) {
        if (loc == null) return "";
        String x = loc.toLowerCase(Locale.ROOT).trim();
        x = x.replaceAll("\\s+", " ");
        return x;
    }

    static String stripOuterQuotes(String s) {
        if (s == null) return "";
        s = s.trim();
        if (s.length() >= 2 && ((s.startsWith("\"") && s.endsWith("\"")) || (s.startsWith("'") && s.endsWith("'")))) {
            return s.substring(1, s.length() - 1);
        }
        return s;
    }

    static String csv(String s) {
        if (s == null) s = "";
        boolean needs = s.contains(",") || s.contains("\"") || s.contains("\n") || s.contains("\r");
        String out = s.replace("\"", "\"\"");
        return needs ? "\"" + out + "\"" : out;
    }

    static String json(String s) {
        if (s == null) return "null";
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '\\': sb.append("\\\\"); break;
                case '"': sb.append("\\\""); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) sb.append(String.format("\\u%04x", (int)c));
                    else sb.append(c);
            }
        }
        sb.append("\"");
        return sb.toString();
    }

    // ---------- Main ----------
    public static void main(String[] args) throws Exception {
        Args a = parseArgs(args);

        List<String> lines = Files.readAllLines(Paths.get(a.inPath), StandardCharsets.UTF_8);
        List<Incident> incidents = parseObservers(lines);

        // Filter first (so hotspot count is based on what you're analyzing)
        List<Incident> filtered = new ArrayList<>();
        for (Incident i : incidents) {
            if (matchesFilters(i, a.location, a.type)) filtered.add(i);
        }

        // Hotspot: count incidents per primary location
        Map<String, Integer> locationCounts = buildLocationCounts(filtered);

        // Sort by hotspot count desc, then provided severity desc
        filtered.sort((x, y) -> {
            String kx = x.primaryLocationKey();
            String ky = y.primaryLocationKey();
            if (kx.isEmpty()) kx = "(unknown)";
            if (ky.isEmpty()) ky = "(unknown)";

            int cx = locationCounts.getOrDefault(kx, 0);
            int cy = locationCounts.getOrDefault(ky, 0);

            // (A) hotspot first
            if (cx != cy) return Integer.compare(cy, cx);

            // (B) severity (provided) next
            if (x.severity == null && y.severity == null) {
                // (C) tie-breaker
                return Integer.compare(x.observerId, y.observerId);
            }
            if (x.severity == null) return 1;
            if (y.severity == null) return -1;

            int sev = Double.compare(y.severity, x.severity);
            if (sev != 0) return sev;

            // (C) tie-breaker
            return Integer.compare(x.observerId, y.observerId);
        });

        Path out = Paths.get(a.outPath);
        if (a.format.equals("csv")) writeCsv(filtered, locationCounts, out);
        else writeJson(filtered, locationCounts, out);

        System.out.println("Wrote " + filtered.size() + " incident(s) to: " + out.toAbsolutePath());
    }
}