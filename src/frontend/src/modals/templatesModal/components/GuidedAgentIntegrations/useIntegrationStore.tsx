import create from 'zustand';
import { persist } from 'zustand/middleware';

interface IntegrationStore {
  gmailConnected: boolean;
  slackConnected: boolean;
  hubspotConnected: boolean;
  apiKey: string | null;
  setGmailConnected: (value: boolean) => void;
  setSlackConnected: (value: boolean) => void;
  setHubSpotConnected: (value: boolean) => void;
  setApiKey: (key: string | null) => void;
  getAuthHeaders: () => Record<string, string>;
}

export const useIntegrationStore = create<IntegrationStore>()(
  persist(
    (set, get) => ({
      gmailConnected: false,
      slackConnected: false,
      hubspotConnected: false,
      apiKey: null,
      setGmailConnected: (value: boolean) => set({ gmailConnected: value }),
      setSlackConnected: (value: boolean) => set({ slackConnected: value }),
      setHubSpotConnected: (value: boolean) => set({ hubspotConnected: value }),
      setApiKey: (key: string | null) => set({ apiKey: key }),
      getAuthHeaders: () => {
        const token = document.cookie
          .split('; ')
          .find(row => row.startsWith('access_token_lf='))
          ?.split('=')[1];

        return {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        };
      },
    }),
    {
      name: 'integration-storage', // name of the item in storage
      getStorage: () => localStorage, // (optional) defaults to localStorage
    }
  )
);