'use client';

import type { LicenseChoice, PublicationConfig, GithubRepo } from '@/lib/types';

interface ConfigDialogProps {
  repos: GithubRepo[];
  initial: PublicationConfig | null;
  onCancel: () => void;
  onSave: (cfg: {
    repo_full_name: string;
    target_subdirectory: string;
    branch: string;
    commit_message_template: string;
    license_choice: LicenseChoice;
  }) => void;
  saving: boolean;
}

const LICENSES: { value: LicenseChoice; label: string }[] = [
  { value: 'none', label: 'Aucune licence' },
  { value: 'polyform-nc', label: 'PolyForm Noncommercial 1.0.0' },
  { value: 'cc-by-nc-sa-4.0', label: 'Creative Commons BY-NC-SA 4.0' },
  { value: 'cc-by-4.0', label: 'Creative Commons BY 4.0' },
  { value: 'mit', label: 'MIT' },
];

export function PublishToGithubConfigDialog({
  repos,
  initial,
  onCancel,
  onSave,
  saving,
}: ConfigDialogProps) {
  return (
    <div
      role="dialog"
      aria-label="Configurer la publication GitHub"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
      }}
    >
      <form
        style={{
          background: 'white',
          padding: '1.5rem 2rem',
          borderRadius: 8,
          minWidth: 480,
          maxWidth: 720,
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
        }}
        onSubmit={(e) => {
          e.preventDefault();
          const fd = new FormData(e.currentTarget);
          onSave({
            repo_full_name: String(fd.get('repo_full_name') ?? ''),
            target_subdirectory: String(fd.get('target_subdirectory') ?? ''),
            branch: String(fd.get('branch') ?? 'main'),
            commit_message_template: String(
              fd.get('commit_message_template') ?? 'Update role {role_name}',
            ),
            license_choice: (fd.get('license_choice') ?? 'none') as LicenseChoice,
          });
        }}
      >
        <h3 style={{ margin: 0, fontSize: '1.125rem' }}>
          Configuration publication GitHub
        </h3>

        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <span style={{ fontSize: '0.85rem' }}>Repo cible</span>
          <select
            name="repo_full_name"
            defaultValue={initial?.repo_full_name ?? repos[0]?.full_name ?? ''}
            required
            style={{ padding: '0.4rem' }}
          >
            {repos.map((r) => (
              <option key={r.full_name} value={r.full_name}>
                {r.full_name}
                {r.private ? ' (privé)' : ''}
              </option>
            ))}
          </select>
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <span style={{ fontSize: '0.85rem' }}>
            Sous-répertoire (ex: <code>roles/ux-designer-clea</code>)
          </span>
          <input
            name="target_subdirectory"
            type="text"
            defaultValue={initial?.target_subdirectory ?? ''}
            required
            style={{ padding: '0.4rem' }}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <span style={{ fontSize: '0.85rem' }}>Branche</span>
          <input
            name="branch"
            type="text"
            defaultValue={initial?.branch ?? 'main'}
            required
            style={{ padding: '0.4rem' }}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <span style={{ fontSize: '0.85rem' }}>
            Template de commit message ({'{role_name}'} sera remplacé)
          </span>
          <input
            name="commit_message_template"
            type="text"
            defaultValue={initial?.commit_message_template ?? 'Update role {role_name}'}
            required
            style={{ padding: '0.4rem' }}
          />
        </label>

        <fieldset
          style={{
            border: '1px solid #e5e7eb',
            borderRadius: 4,
            padding: '0.5rem 0.75rem',
            margin: 0,
          }}
        >
          <legend style={{ fontSize: '0.85rem', padding: '0 0.25rem' }}>
            Licence du rôle publié
          </legend>
          {LICENSES.map((opt) => (
            <label
              key={opt.value}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                fontSize: '0.85rem',
                padding: '0.15rem 0',
              }}
            >
              <input
                type="radio"
                name="license_choice"
                value={opt.value}
                defaultChecked={(initial?.license_choice ?? 'none') === opt.value}
              />
              {opt.label}
            </label>
          ))}
        </fieldset>

        <div
          style={{
            display: 'flex',
            gap: '0.5rem',
            justifyContent: 'flex-end',
            marginTop: '0.5rem',
          }}
        >
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: '0.4rem 0.9rem',
              border: '1px solid #d1d5db',
              borderRadius: 4,
              background: 'white',
              cursor: 'pointer',
            }}
          >
            Annuler
          </button>
          <button
            type="submit"
            disabled={saving}
            style={{
              padding: '0.4rem 0.9rem',
              background: '#2563eb',
              color: 'white',
              border: 0,
              borderRadius: 4,
              cursor: saving ? 'not-allowed' : 'pointer',
              opacity: saving ? 0.6 : 1,
              fontWeight: 600,
            }}
          >
            {saving ? 'Enregistrement…' : 'Enregistrer'}
          </button>
        </div>
      </form>
    </div>
  );
}
