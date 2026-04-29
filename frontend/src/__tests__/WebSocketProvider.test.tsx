import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { WebSocketProvider } from '@/components/WebSocketProvider';
import { wsManager } from '@/lib/ws/connection';

// Mock next-auth/react useSession — déclaré au top-level pour éviter le hoist.
const useSessionMock = vi.fn();
vi.mock('next-auth/react', () => ({
  useSession: () => useSessionMock(),
}));

describe('WebSocketProvider', () => {
  // Types inférés depuis vi.spyOn — vitest les génère trop strictement pour
  // une annotation manuelle propre.
  let connectSpy = vi.spyOn(wsManager, 'connect');
  let disconnectSpy = vi.spyOn(wsManager, 'disconnect');

  beforeEach(() => {
    connectSpy = vi.spyOn(wsManager, 'connect').mockImplementation(() => {});
    disconnectSpy = vi.spyOn(wsManager, 'disconnect').mockImplementation(() => {});
    useSessionMock.mockReset();
  });

  afterEach(() => {
    connectSpy.mockRestore();
    disconnectSpy.mockRestore();
  });

  it('ne connecte pas si la session est en loading', () => {
    useSessionMock.mockReturnValue({ data: null, status: 'loading' });
    render(
      <WebSocketProvider>
        <div>child</div>
      </WebSocketProvider>,
    );
    expect(connectSpy).not.toHaveBeenCalled();
  });

  it('ne connecte pas si l\'utilisateur n\'est pas authentifié', () => {
    useSessionMock.mockReturnValue({ data: null, status: 'unauthenticated' });
    render(
      <WebSocketProvider>
        <div>child</div>
      </WebSocketProvider>,
    );
    expect(connectSpy).not.toHaveBeenCalled();
  });

  it('connecte avec le token en query param quand la session est OK', async () => {
    useSessionMock.mockReturnValue({
      data: { accessToken: 'ghp_secret_abc' },
      status: 'authenticated',
    });
    render(
      <WebSocketProvider>
        <div>child</div>
      </WebSocketProvider>,
    );
    await waitFor(() => expect(connectSpy).toHaveBeenCalled());
    const url = (connectSpy.mock.calls[0]?.[0] ?? '') as string;
    expect(url).toContain('/ws?token=ghp_secret_abc');
    expect(url.startsWith('ws://') || url.startsWith('wss://')).toBe(true);
  });

  it('disconnect au unmount', () => {
    useSessionMock.mockReturnValue({
      data: { accessToken: 'tok' },
      status: 'authenticated',
    });
    const { unmount } = render(
      <WebSocketProvider>
        <div>child</div>
      </WebSocketProvider>,
    );
    unmount();
    expect(disconnectSpy).toHaveBeenCalled();
  });

  it('rend les enfants', () => {
    useSessionMock.mockReturnValue({ data: null, status: 'unauthenticated' });
    const { getByText } = render(
      <WebSocketProvider>
        <div>visible-child</div>
      </WebSocketProvider>,
    );
    expect(getByText('visible-child')).toBeInTheDocument();
  });
});
