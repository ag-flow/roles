import type { ReactNode } from 'react';
import { Providers } from '@/components/Providers';

export const metadata = {
  title: 'Role Builder',
  description: 'Construction de rôles ag.flow depuis des corpus audio scrapés',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body style={{ margin: 0, fontFamily: 'system-ui, sans-serif' }}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
