import { create } from "zustand";

interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  login: (token: string) => void;
  logout: () => void;
}

/**
 * Auth store — manages JWT token in memory and localStorage.
 * Initializes from localStorage for session persistence across reloads.
 */
export const useAuthStore = create<AuthState>((set) => {
  const storedToken = localStorage.getItem("jobbi_token");

  return {
    token: storedToken,
    isAuthenticated: storedToken !== null,

    login: (token: string) => {
      localStorage.setItem("jobbi_token", token);
      set({ token, isAuthenticated: true });
    },

    logout: () => {
      localStorage.removeItem("jobbi_token");
      set({ token: null, isAuthenticated: false });
    },
  };
});
