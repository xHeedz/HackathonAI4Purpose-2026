import java.util.Collections;
import java.util.Set;

enum Role { VICTIM, OBSERVER }

enum Urgency {
    NOT_SURE(0.3),
    URGENT(0.7),
    LIFE_THREATENING(1.0);

    final double score;
    Urgency(double score) { this.score = score; }
}

enum PeopleRange {
    ONE_TO_TWO(0.3),
    THREE_TO_TEN(0.7),
    TEN_PLUS(1.0);

    final double score;
    PeopleRange(double score) { this.score = score; }
}

enum EventType { FIRE, BOMBING, FLOOD, EARTHQUAKE, TORNADO, OTHER }

enum SeverityColor { GREEN, YELLOW, ORANGE, RED }

public class SeverityCalculator {

    public static double calculateSeverity(
            EventType event,
            Role role,
            Urgency urgency,
            PeopleRange peopleRange,   // may be null
            Set<String> indicators,    // may be null
            boolean debug
    ) {
        Set<String> safeIndicators = (indicators == null) ? Collections.emptySet() : indicators;

        double U = urgency.score;
        double P = (peopleRange != null) ? peopleRange.score : defaultPeopleScore(event);
        double R = (role == Role.VICTIM) ? 1.0 : 0.8;
        double D = dangerScore(event, safeIndicators);

        double base01 = baseScore01(event, U, D, P, R);
        double severity = clamp(100.0 * base01, 0.0, 100.0);

        if (debug) {
            System.out.println("----- DEBUG -----");
            System.out.println("Event=" + event);
            System.out.println("Role=" + role + " => R=" + R);
            System.out.println("Urgency=" + urgency + " => U=" + U);
            System.out.println("PeopleRange=" + (peopleRange == null ? "null(default)" : peopleRange) + " => P=" + P);
            System.out.println("Indicators=" + safeIndicators);
            System.out.println("DangerScore D=" + D);
            System.out.println("Base(0..1)=" + base01);
            System.out.println("Severity(0..100)=" + severity);
            System.out.println("-----------------");
        }

        return severity;
    }

    // Map severity to color (same mapping we used)
    public static SeverityColor colorFor(double severity) {
        if (severity >= 85) return SeverityColor.RED;
        if (severity >= 65) return SeverityColor.ORANGE;
        if (severity >= 40) return SeverityColor.YELLOW;
        return SeverityColor.GREEN;
    }

    // Base = 100*(aU*U + bD*D + cP*P + dR*R)
    private static double baseScore01(EventType event, double U, double D, double P, double R) {
        return switch (event) {
            case FIRE       -> 0.35*U + 0.30*D + 0.20*P + 0.15*R;
            case BOMBING    -> 0.40*U + 0.35*D + 0.15*P + 0.10*R;
            case FLOOD      -> 0.35*U + 0.35*D + 0.20*P + 0.10*R;
            case EARTHQUAKE -> 0.35*U + 0.40*D + 0.15*P + 0.10*R;
            case TORNADO    -> 0.40*U + 0.35*D + 0.15*P + 0.10*R;
            case OTHER      -> 0.40*U + 0.30*D + 0.20*P + 0.10*R;
        };
    }

    // D = min(1, sum of indicator weights)
    private static double dangerScore(EventType event, Set<String> indicators) {
        if (indicators == null || indicators.isEmpty()) return 0.0;

        double sum = 0.0;
        for (String key : indicators) {
            sum += switch (event) {
                case FIRE -> fireWeights(key);
                case BOMBING -> bombingWeights(key);
                case FLOOD -> floodWeights(key);
                case EARTHQUAKE -> earthquakeWeights(key);
                case TORNADO -> tornadoWeights(key);
                case OTHER -> otherWeights(key);
            };
        }
        return Math.min(1.0, sum);
    }

    // ---------- Indicator weights ----------
    private static double fireWeights(String k) {
        return switch (k) {
            case "injured" -> 0.3;
            case "trapped" -> 0.4;
            case "fire_spreading" -> 0.4;
            case "heavy_smoke" -> 0.3;
            case "vulnerable" -> 0.3;
            default -> 0.0;
        };
    }
    private static double bombingWeights(String k) {
        return switch (k) {
            case "injured" -> 0.4;
            case "trapped" -> 0.5;
            case "building_damage" -> 0.4;
            case "major_explosion" -> 0.5;
            case "secondary_fire" -> 0.3;
            default -> 0.0;
        };
    }
    private static double floodWeights(String k) {
        return switch (k) {
            case "trapped" -> 0.4;
            case "water_in_homes" -> 0.4;
            case "fast_water" -> 0.5;
            case "vehicles_swept" -> 0.4;
            case "vulnerable" -> 0.3;
            default -> 0.0;
        };
    }
    private static double earthquakeWeights(String k) {
        return switch (k) {
            case "buildings_collapsed" -> 0.5;
            case "trapped" -> 0.5;
            case "structural_damage" -> 0.4;
            case "aftershocks" -> 0.3;
            case "vulnerable" -> 0.3;
            default -> 0.0;
        };
    }
    private static double tornadoWeights(String k) {
        return switch (k) {
            case "visible_funnel" -> 0.5;
            case "building_damage" -> 0.4;
            case "trapped" -> 0.4;
            case "flying_debris" -> 0.4;
            case "vulnerable" -> 0.3;
            default -> 0.0;
        };
    }
    private static double otherWeights(String k) {
        return switch (k) {
            case "injured" -> 0.4;
            case "trapped" -> 0.4;
            case "immediate_danger" -> 0.5;
            case "infrastructure_damage" -> 0.3;
            case "vulnerable" -> 0.3;
            default -> 0.0;
        };
    }

    private static double defaultPeopleScore(EventType event) {
        return switch (event) {
            case FIRE, OTHER -> 0.4;
            case BOMBING, FLOOD -> 0.5;
            case EARTHQUAKE, TORNADO -> 0.6;
        };
    }

    private static double clamp(double x, double lo, double hi) {
        return Math.max(lo, Math.min(hi, x));
    }
}
