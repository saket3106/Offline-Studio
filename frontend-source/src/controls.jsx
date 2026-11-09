import React, { Children, isValidElement, useId } from "react";
import { Select } from "@base-ui/react/select";
import { Check, ChevronDown, ChevronUp } from "lucide-react";

// Render the popup in the document, rather than delegating its colors and
// geometry to Qt's platform-native <select> popup.
export function ThemedSelect({
  label,
  name,
  value,
  options,
  onChange,
  disabled = false,
  className = "",
}) {
  const selected = options.find(([key]) => String(key) === String(value));
  return (
    <Select.Root
      name={name}
      value={value}
      disabled={disabled}
      items={options.map(([key, text]) => ({ value: key, label: text }))}
      onValueChange={(next) => {
        if (next !== null) onChange?.(next);
      }}
    >
      <Select.Trigger
        className={`themed-select-trigger ${className}`}
        aria-label={label}
      >
        <Select.Value>
          {selected?.[1] ??
            (value ? `Unavailable: ${value}` : "Choose an option")}
        </Select.Value>
        <Select.Icon>
          <ChevronDown size={15} aria-hidden="true" />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner
          className="themed-select-positioner"
          sideOffset={5}
          alignItemWithTrigger={false}
        >
          <Select.Popup className="themed-select-popup">
            <Select.ScrollUpArrow className="themed-select-scroll-arrow">
              <ChevronUp size={14} />
            </Select.ScrollUpArrow>
            <Select.List className="themed-select-list">
              {options.map(([key, text, unavailable = false]) => (
                <Select.Item
                  className="themed-select-item"
                  key={String(key)}
                  value={key}
                  disabled={unavailable}
                >
                  <Select.ItemText>{text}</Select.ItemText>
                  <Select.ItemIndicator>
                    <Check size={14} aria-hidden="true" />
                  </Select.ItemIndicator>
                </Select.Item>
              ))}
            </Select.List>
            <Select.ScrollDownArrow className="themed-select-scroll-arrow">
              <ChevronDown size={14} />
            </Select.ScrollDownArrow>
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}

// Migration adapter preserves existing form event contracts without native popups.
export function SelectField({
  children,
  value,
  onChange,
  name,
  disabled,
  className = "",
  id,
  ...rest
}) {
  const generated = useId();
  const flatten = (nodes) =>
    Children.toArray(nodes).flatMap((node) => {
      if (!isValidElement(node)) return [];
      if (node.type === "option")
        return [
          [
            String(node.props.value ?? node.props.children),
            node.props.children,
            !!node.props.disabled,
          ],
        ];
      return flatten(node.props.children);
    });
  const options = flatten(children);
  return (
    <span className="select-field" id={id || generated} title={rest.title}>
      <ThemedSelect
        label={rest["aria-label"] || name || "Choose an option"}
        name={name}
        value={String(value ?? "")}
        options={options}
        disabled={disabled}
        className={className}
        onChange={(next) =>
          onChange?.({
            target: { name, value: next },
            currentTarget: { name, value: next },
          })
        }
      />
    </span>
  );
}
