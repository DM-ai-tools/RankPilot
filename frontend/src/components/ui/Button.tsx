import type { ButtonHTMLAttributes, ReactNode } from "react";

const variants = {
  primary: "text-white shadow-sm",
  navy:    "text-white shadow-sm",
  outline: "border border-rp-border bg-white text-navy",
  teal:    "text-white shadow-sm",
} as const;

const filledStyle = { backgroundColor: "#72C219" } as const;
const outlineHoverClass = "hover:border-[#72C219] hover:text-[#72C219]";

type Variant = keyof typeof variants;

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md";
  children: ReactNode;
};

export function Button({ variant = "primary", size = "md", className = "", style, ...props }: Props) {
  const sz =
    size === "sm"
      ? "rounded-lg px-3 py-1.5 text-xs font-semibold"
      : "rounded-lg px-[18px] py-2.5 text-[13px] font-semibold";

  const isFilled = variant !== "outline";
  const extraClass = variant === "outline" ? outlineHoverClass : "";

  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-1.5 font-semibold transition-colors disabled:opacity-50 ${variants[variant]} ${sz} ${extraClass} ${className}`}
      style={isFilled ? { ...filledStyle, ...style } : style}
      {...props}
    />
  );
}
