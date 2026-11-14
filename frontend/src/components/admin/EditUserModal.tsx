import { useState, type FormEvent } from 'react';
import api, { errorMessage, type AdminUser } from '../../services/api';
import { useAuth } from '../../contexts/AuthContext';
import { Button, Field, Input, Modal, Notice, Select } from '../../ui';
import { toast } from '../../utils/toast';
import { ROLE_HINT, ROLE_LABEL, canManage, grantableRoles, type Role } from './roles';

/** Name, role and email-verified flag. Status and deletion live in the row menu. */
export default function EditUserModal({ member, onClose, onSaved }: { member: AdminUser; onClose: () => void; onSaved: () => void }) {
  const { user } = useAuth();
  const manageable = canManage(user, member);
  const roles = grantableRoles(user);
  const [fullName, setFullName] = useState(member.full_name ?? '');
  const [role, setRole] = useState(member.role as Role);
  const [verified, setVerified] = useState(member.is_verified);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const changes: { full_name?: string; role?: string; is_verified?: boolean } = {};
  if (fullName.trim() !== (member.full_name ?? '')) changes.full_name = fullName.trim();
  if (manageable && role !== member.role) changes.role = role;
  if (manageable && verified !== member.is_verified) changes.is_verified = verified;
  const dirty = Object.keys(changes).length > 0;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!dirty) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateUser(member.id, changes);
      toast.success('Member updated');
      onSaved();
      onClose();
    } catch (err) {
      setError(errorMessage(err, 'Could not update the member'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      dismissible={!saving}
      title="Edit member"
      description={member.email}
      footer={
        <>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button type="submit" form="edit-user" loading={saving} disabled={!dirty}>Save</Button>
        </>
      }
    >
      <form id="edit-user" onSubmit={submit} className="space-y-4" noValidate>
        {error && <Notice tone="error">{error}</Notice>}
        <Field label="Full name">
          <Input value={fullName} onChange={(e) => setFullName(e.target.value)} maxLength={255} data-autofocus />
        </Field>
        {manageable ? (
          <>
            <Field label="Role" hint={ROLE_HINT[role]}>
              <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
                {roles.map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
              </Select>
            </Field>
            <label className="flex items-start gap-3 text-small text-ink">
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--primary))]" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
              <span>
                <span className="font-semibold">Email verified</span>
                <span className="block text-ink-muted">Mark verified only if you know the address belongs to this person.</span>
              </span>
            </label>
          </>
        ) : (
          <p className="text-small text-ink-muted">
            {member.id === user?.id
              ? 'You cannot change your own role or verification.'
              : `Only the platform operator can change a ${ROLE_LABEL[member.role]?.toLowerCase() ?? member.role}.`}
          </p>
        )}
      </form>
    </Modal>
  );
}
