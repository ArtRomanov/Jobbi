import {
  Document,
  Page,
  Text,
  View,
  StyleSheet,
} from "@react-pdf/renderer";
import type { Cv } from "@/entities/cv";

const styles = StyleSheet.create({
  page: {
    padding: 40,
    fontSize: 10,
    fontFamily: "Helvetica",
    color: "#1a1a1a",
  },
  header: {
    marginBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: "#d1d5db",
    paddingBottom: 12,
  },
  name: {
    fontSize: 22,
    fontFamily: "Helvetica-Bold",
    marginBottom: 4,
  },
  contactRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
    fontSize: 9,
    color: "#374151",
  },
  sectionTitle: {
    fontSize: 12,
    fontFamily: "Helvetica-Bold",
    marginTop: 14,
    marginBottom: 6,
    color: "#2563eb",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  paragraph: {
    marginBottom: 6,
    lineHeight: 1.4,
  },
  entryHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  entryTitle: {
    fontFamily: "Helvetica-Bold",
    fontSize: 10,
  },
  entrySubtitle: {
    fontSize: 9,
    color: "#6b7280",
  },
  entryDescription: {
    marginTop: 3,
    marginBottom: 8,
    lineHeight: 1.4,
    fontSize: 9,
  },
});

interface CvDocumentProps {
  cv: Cv;
}

/**
 * React-PDF document component that renders a CV as a professional PDF.
 * Lazy-loaded at the call site to keep the main bundle small.
 */
export function CvDocument({ cv }: CvDocumentProps) {
  const info = cv.personal_info;
  const contactParts: string[] = [];
  if (info?.email) contactParts.push(info.email);
  if (info?.phone) contactParts.push(info.phone);
  if (info?.location) contactParts.push(info.location);
  if (info?.linkedin_url) contactParts.push(info.linkedin_url);

  return (
    <Document>
      <Page size="A4" style={styles.page}>
        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.name}>
            {info?.full_name || cv.name}
          </Text>
          {contactParts.length > 0 && (
            <View style={styles.contactRow}>
              <Text>{contactParts.join("  |  ")}</Text>
            </View>
          )}
        </View>

        {/* Summary */}
        {cv.summary ? (
          <>
            <Text style={styles.sectionTitle}>Summary</Text>
            <Text style={styles.paragraph}>{cv.summary}</Text>
          </>
        ) : null}

        {/* Work Experience */}
        {cv.work_experience && cv.work_experience.length > 0 ? (
          <>
            <Text style={styles.sectionTitle}>Work Experience</Text>
            {cv.work_experience.map((w, i) => (
              <View key={i}>
                <View style={styles.entryHeader}>
                  <Text style={styles.entryTitle}>
                    {w.role} at {w.company}
                  </Text>
                  <Text style={styles.entrySubtitle}>
                    {w.start_date ?? ""}
                    {w.start_date && (w.end_date || w.is_current) ? " - " : ""}
                    {w.is_current ? "Present" : (w.end_date ?? "")}
                  </Text>
                </View>
                {w.description ? (
                  <Text style={styles.entryDescription}>
                    {w.description}
                  </Text>
                ) : null}
              </View>
            ))}
          </>
        ) : null}

        {/* Education */}
        {cv.education && cv.education.length > 0 ? (
          <>
            <Text style={styles.sectionTitle}>Education</Text>
            {cv.education.map((e, i) => (
              <View key={i}>
                <View style={styles.entryHeader}>
                  <Text style={styles.entryTitle}>
                    {e.degree ? `${e.degree}${e.field_of_study ? ` in ${e.field_of_study}` : ""}` : e.institution}
                  </Text>
                  <Text style={styles.entrySubtitle}>
                    {e.start_year ?? ""}
                    {e.start_year && e.end_year ? " - " : ""}
                    {e.end_year ?? ""}
                  </Text>
                </View>
                {e.degree ? (
                  <Text style={styles.entrySubtitle}>{e.institution}</Text>
                ) : null}
                {e.description ? (
                  <Text style={styles.entryDescription}>
                    {e.description}
                  </Text>
                ) : null}
              </View>
            ))}
          </>
        ) : null}

        {/* Skills */}
        {cv.skills ? (
          <>
            <Text style={styles.sectionTitle}>Skills</Text>
            <Text style={styles.paragraph}>{cv.skills}</Text>
          </>
        ) : null}

        {/* Languages */}
        {cv.languages ? (
          <>
            <Text style={styles.sectionTitle}>Languages</Text>
            <Text style={styles.paragraph}>{cv.languages}</Text>
          </>
        ) : null}
      </Page>
    </Document>
  );
}
