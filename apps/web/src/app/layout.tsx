import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {title:'Aster · Enterprise knowledge',description:'Answers grounded in your organization’s knowledge.'};

// This is fixed, authored markup for the design record. It contains no runtime or user content.
const designRecord = `<!--
THESIS: Treat each answer as a readable passage connected to its evidence.
OWN-WORLD: Warm paper and ruled surfaces, navy text, cobalt controls, and Source Serif 4 headings.
STORY: Ask, read, select a citation, and inspect the excerpt or original file.
FIRST VIEWPORT: Navigation at left, reading and composer in the middle, source index at right. On phones, sources open in a sheet.
FORM: Editorial reference desk, user-selected direction. Operate concept seed c51708ef, assigned index 3.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
-->`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>
    <div hidden aria-hidden="true" dangerouslySetInnerHTML={{ __html: designRecord }} />
    {children}
  </body></html>;
}
