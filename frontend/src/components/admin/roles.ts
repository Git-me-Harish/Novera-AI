/**
 * Client copy of app/services/tenancy/roles.py so the UI only offers what the
 * server will accept. The server stays the authority; this avoids dead ends.
 */
export type Role = 'user' | 'admin' | 'org_admin' | 'super_admin';

export const ROLE_LABEL: Record<string, string> = {
  user: 'Member',
  admin: 'Administrator',
  org_admin: 'Organization owner',
  super_admin: 'Platform administrator',
};

export const ROLE_HINT: Record<string, string> = {
  user: 'Asks questions and reads documents.',
  admin: 'Also uploads documents and manages members, models and branding.',
  org_admin: 'An administrator only the platform operator can appoint or remove.',
};

interface Person { id: string; role: string }

export const isSuper = (actor?: Person | null) => actor?.role === 'super_admin';

/** Roles the actor may hand out (create, invite, change). */
export function grantableRoles(actor?: Person | null): Role[] {
  return isSuper(actor) ? ['user', 'admin', 'org_admin'] : ['user', 'admin'];
}

/** May the actor change this member's role, status or account? */
export function canManage(actor: Person | null | undefined, target: Person): boolean {
  if (!actor || actor.id === target.id) return false;
  if (isSuper(actor)) return true;
  return target.role !== 'org_admin' && target.role !== 'super_admin';
}

/** Mirrors the reset-password endpoint: org owners only by a super admin. */
export function canResetPassword(actor: Person | null | undefined, target: Person): boolean {
  if (!actor || actor.id === target.id) return false;
  if (isSuper(actor)) return true;
  return target.role !== 'org_admin' && target.role !== 'super_admin';
}
