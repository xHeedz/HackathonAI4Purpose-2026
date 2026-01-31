import java.util.*;

public class KeywordAI {

    // ---------- Public function ----------
    public static ExtractionResult extract(String text) {
        if (text == null) text = "";
        String t = normalize(text);

        EventType event = detectEventType(t);
        Set<String> indicators = detectIndicators(event, t);

        return new ExtractionResult(event, indicators);
    }

    // ---------- Result container ----------
    public static class ExtractionResult {
        public final EventType eventType;
        public final Set<String> indicators;

        public ExtractionResult(EventType eventType, Set<String> indicators) {
            this.eventType = eventType;
            this.indicators = indicators;
        }
    }

    // ---------- Normalize ----------
    private static String normalize(String s) {
        // lowercase, remove punctuation-ish, collapse spaces
        s = s.toLowerCase(Locale.ROOT);
        s = s.replaceAll("[^a-z0-9\\s]", " ");
        s = s.replaceAll("\\s+", " ").trim();
        return s;
    }

    // ---------- Detect Event Type (optional but useful) ----------
    private static EventType detectEventType(String t) {
        // Score keywords per event and pick the max.
        int fire = scoreAny(t, "fire", "burning", "smoke", "flames");
        int bombing = scoreAny(t, "explosion", "bomb", "blast", "detonation");
        int flood = scoreAny(t, "flood", "water rising", "inundated", "overflow");
        int quake = scoreAny(t, "earthquake", "shake", "tremor", "aftershock");
        int tornado = scoreAny(t, "tornado", "funnel", "twister", "cyclone");

        int max = Math.max(fire, Math.max(bombing, Math.max(flood, Math.max(quake, tornado))));
        if (max == 0) return EventType.OTHER;

        if (max == fire) return EventType.FIRE;
        if (max == bombing) return EventType.BOMBING;
        if (max == flood) return EventType.FLOOD;
        if (max == quake) return EventType.EARTHQUAKE;
        return EventType.TORNADO;
    }

    private static int scoreAny(String t, String... phrases) {
        int score = 0;
        for (String p : phrases) {
            if (t.contains(p)) score++;
        }
        return score;
    }

    // ---------- Detect Indicators based on event ----------
    private static Set<String> detectIndicators(EventType event, String t) {
        Set<String> out = new HashSet<>();

        // Common indicators across many events
        if (hasAny(t, "injured", "hurt", "wounded", "bleeding")) out.add("injured");
        if (hasAny(t, "trapped", "stuck", "cant get out", "cannot get out", "blocked")) out.add("trapped");
        if (hasAny(t, "children", "baby", "elderly", "old people", "disabled")) out.add("vulnerable");

        // Event-specific
        switch (event) {
            case FIRE -> {
                if (hasAny(t, "smoke", "heavy smoke", "cant breathe")) out.add("heavy_smoke");
                if (hasAny(t, "spreading", "getting bigger", "growing fast")) out.add("fire_spreading");
                // optional: if text mentions flames
                if (hasAny(t, "flames", "burning")) { /* no extra indicator needed */ }
            }
            case BOMBING -> {
                if (hasAny(t, "building damaged", "collapsed wall", "broken building", "destroyed")) out.add("building_damage");
                if (hasAny(t, "major", "huge blast", "big explosion", "massive")) out.add("major_explosion");
                if (hasAny(t, "fire", "burning after", "secondary fire")) out.add("secondary_fire");
            }
            case FLOOD -> {
                if (hasAny(t, "water in home", "water inside", "entered house", "in my house")) out.add("water_in_homes");
                if (hasAny(t, "fast water", "strong current", "rapid water", "water rushing")) out.add("fast_water");
                if (hasAny(t, "car swept", "cars floating", "vehicle swept", "car drifting")) out.add("vehicles_swept");
            }
            case EARTHQUAKE -> {
                if (hasAny(t, "collapsed", "building collapsed", "house collapsed")) out.add("buildings_collapsed");
                if (hasAny(t, "structural damage", "cracks", "walls cracked", "columns cracked")) out.add("structural_damage");
                if (hasAny(t, "aftershock", "aftershocks")) out.add("aftershocks");
            }
            case TORNADO -> {
                if (hasAny(t, "funnel", "visible tornado", "twister", "tornado")) out.add("visible_funnel");
                if (hasAny(t, "debris", "flying debris", "objects flying")) out.add("flying_debris");
                if (hasAny(t, "building damage", "roof gone", "destroyed houses")) out.add("building_damage");
            }
            case OTHER -> {
                if (hasAny(t, "immediate danger", "danger", "urgent", "help now")) out.add("immediate_danger");
                if (hasAny(t, "bridge damaged", "road collapsed", "power station", "infrastructure")) out.add("infrastructure_damage");
            }
        }

        return out;
    }

    private static boolean hasAny(String t, String... phrases) {
        for (String p : phrases) {
            if (t.contains(p)) return true;
        }
        return false;
    }

    // ---------- Use the same enums as your SeverityCalculator ----------
    public enum EventType { FIRE, BOMBING, FLOOD, EARTHQUAKE, TORNADO, OTHER }
}
import java.util.*;

public class FuzzyMatch {

    // Returns true if ANY token in text is close to keyword
    public static boolean containsFuzzy(String text, String keyword, int maxDist) {
        if (text == null || keyword == null) return false;

        String t = normalize(text);
        String k = normalize(keyword);

        for (String token : t.split(" ")) {
            if (token.isBlank()) continue;

            // quick exact match shortcut
            if (token.equals(k)) return true;

            // only compare reasonably sized tokens (avoid nonsense)
            if (Math.abs(token.length() - k.length()) > maxDist) continue;

            int d = levenshtein(token, k);
            if (d <= maxDist) return true;
        }
        return false;
    }

    private static String normalize(String s) {
        s = s.toLowerCase(Locale.ROOT);
        s = s.replaceAll("[^a-z0-9\\s]", " ");
        s = s.replaceAll("\\s+", " ").trim();
        return s;
    }

    // Standard Levenshtein distance (edit distance)
    public static int levenshtein(String a, String b) {
        int n = a.length(), m = b.length();
        int[][] dp = new int[n + 1][m + 1];

        for (int i = 0; i <= n; i++) dp[i][0] = i;
        for (int j = 0; j <= m; j++) dp[0][j] = j;

        for (int i = 1; i <= n; i++) {
            char ca = a.charAt(i - 1);
            for (int j = 1; j <= m; j++) {
                char cb = b.charAt(j - 1);
                int cost = (ca == cb) ? 0 : 1;
                dp[i][j] = Math.min(
                        Math.min(dp[i - 1][j] + 1, dp[i][j - 1] + 1),
                        dp[i - 1][j - 1] + cost
                );
            }
        }
        return dp[n][m];
    }
}
