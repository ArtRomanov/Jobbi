import { forwardRef, type ReactNode } from "react";
import { Link, type LinkProps } from "react-router-dom";
import { getButtonStyle, type ButtonVariant } from "./button-styles";

interface ButtonLinkProps extends LinkProps {
  children: ReactNode;
  variant?: ButtonVariant;
}

/**
 * A router link that looks like a `Button`. Use it for navigation instead of
 * nesting a `<button>` inside a `<Link>` (two focus stops, invalid HTML).
 */
export const ButtonLink = forwardRef<HTMLAnchorElement, ButtonLinkProps>(
  function ButtonLink({ children, variant = "primary", style, ...rest }, ref) {
    return (
      <Link ref={ref} style={{ ...getButtonStyle(variant), ...style }} {...rest}>
        {children}
      </Link>
    );
  },
);
