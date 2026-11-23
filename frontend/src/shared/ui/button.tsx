import {
  forwardRef,
  type ButtonHTMLAttributes,
  type MouseEvent,
  type ReactNode,
} from "react";
import { getButtonStyle, type ButtonVariant } from "./button-styles";
import { VISUALLY_HIDDEN_STYLE } from "./visually-hidden";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  loading?: boolean;
  variant?: ButtonVariant;
  /**
   * While disabled (or loading), stay focusable: `aria-disabled="true"`
   * instead of the `disabled` attribute, and clicks (or a form's implicit
   * submit) are swallowed. Use it where the button disables itself right
   * after being pressed, so keyboard focus is not dropped to <body>.
   */
  keepFocusable?: boolean;
}

/** Styled button. Forwards its ref so callers can manage focus. */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    children,
    loading = false,
    variant = "primary",
    keepFocusable = false,
    disabled,
    style,
    onClick,
    ...rest
  },
  ref,
) {
  const isDisabled = Boolean(disabled || loading);
  const isSoftDisabled = keepFocusable && isDisabled;

  function handleClick(event: MouseEvent<HTMLButtonElement>): void {
    if (isSoftDisabled) {
      // No action and no form submit while it can't act
      event.preventDefault();
      return;
    }
    onClick?.(event);
  }

  return (
    <button
      ref={ref}
      disabled={isDisabled && !keepFocusable}
      aria-disabled={isSoftDisabled || undefined}
      aria-busy={loading || undefined}
      onClick={handleClick}
      style={{
        ...getButtonStyle(variant, isDisabled),
        ...style,
      }}
      {...rest}
    >
      {loading ? (
        <>
          {/* Visible "Loading..." while the accessible name stays the label */}
          <span aria-hidden="true">Loading...</span>
          <span style={VISUALLY_HIDDEN_STYLE}>{children}</span>
        </>
      ) : (
        children
      )}
    </button>
  );
});
