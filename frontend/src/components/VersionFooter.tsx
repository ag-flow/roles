import { getFrontendVersion } from '@/lib/api/version';

/**
 * Footer minimaliste affichant la version frontend (lue depuis package.json
 * à la compilation). Server Component — pas d'appel réseau, pas de hooks.
 *
 * Pour montrer aussi la version backend en plus, créer un client component
 * avec SWR sur ``getBackendVersion()`` (cf. lib/api/version.ts) ; pour MVP
 * la version frontend suffit comme signature visible.
 */
export function VersionFooter() {
  const v = getFrontendVersion();
  return (
    <footer
      style={{
        textAlign: 'center',
        padding: '0.5rem',
        fontSize: '0.7rem',
        color: '#9ca3af',
        borderTop: '1px solid #f3f4f6',
        marginTop: '2rem',
      }}
    >
      Role Builder v{v}
    </footer>
  );
}
