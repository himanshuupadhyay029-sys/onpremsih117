import React, { useState, useRef, useEffect } from 'react';

/**
 * SovereignSelect - Sovereign Industrial Workbench styled dropdown.
 * Replaces raw OS combobox popups with an elegant, pill-shaped, accessible dropdown
 * featuring subtle spring animations, chevron rotation, and checkmark indicators.
 */
export default function SovereignSelect({
  value,
  onChange,
  options = [],
  placeholder = 'Select option...',
  id,
  className = '',
  style = {},
  align = 'left',
  disabled = false,
  ariaLabel,
  onOpenChange,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const containerRef = useRef(null);
  const listRef = useRef(null);

  const updateIsOpen = (nextState) => {
    const resolved = typeof nextState === 'function' ? nextState(isOpen) : nextState;
    setIsOpen(resolved);
    if (onOpenChange) {
      onOpenChange(resolved);
    }
  };

  // Normalize options to [{ value, label, disabled }]
  const normalizedOptions = options.map((opt) => {
    if (typeof opt === 'string' || typeof opt === 'number') {
      return { value: String(opt), label: String(opt), disabled: false };
    }
    return {
      value: String(opt.value),
      label: opt.label !== undefined ? String(opt.label) : String(opt.value),
      disabled: Boolean(opt.disabled),
    };
  });

  const selectedOption = normalizedOptions.find((opt) => opt.value === String(value));

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        updateIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, [isOpen]);

  // Keep highlighted option scrolled into view
  useEffect(() => {
    if (isOpen && highlightIndex >= 0 && listRef.current) {
      const items = listRef.current.querySelectorAll('.sov-select-item');
      if (items[highlightIndex]) {
        items[highlightIndex].scrollIntoView({ block: 'nearest' });
      }
    }
  }, [isOpen, highlightIndex]);

  const handleToggle = () => {
    if (disabled) return;
    if (!isOpen) {
      const curIdx = normalizedOptions.findIndex((opt) => opt.value === String(value));
      setHighlightIndex(curIdx >= 0 ? curIdx : 0);
    }
    updateIsOpen((prev) => !prev);
  };

  const handleSelect = (optVal) => {
    if (disabled) return;
    updateIsOpen(false);
    if (onChange) {
      // Support standard onChange event shape
      onChange({ target: { value: optVal, id, name: id } });
    }
  };

  const handleKeyDown = (e) => {
    if (disabled) return;

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (!isOpen) {
        updateIsOpen(true);
        setHighlightIndex(0);
      } else {
        setHighlightIndex((prev) => {
          let next = prev + 1;
          while (next < normalizedOptions.length && normalizedOptions[next]?.disabled) {
            next++;
          }
          return next < normalizedOptions.length ? next : prev;
        });
      }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (!isOpen) {
        updateIsOpen(true);
        setHighlightIndex(normalizedOptions.length - 1);
      } else {
        setHighlightIndex((prev) => {
          let prevIdx = prev - 1;
          while (prevIdx >= 0 && normalizedOptions[prevIdx]?.disabled) {
            prevIdx--;
          }
          return prevIdx >= 0 ? prevIdx : prev;
        });
      }
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      if (isOpen && highlightIndex >= 0 && normalizedOptions[highlightIndex]) {
        const item = normalizedOptions[highlightIndex];
        if (!item.disabled) {
          handleSelect(item.value);
        }
      } else {
        handleToggle();
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      updateIsOpen(false);
    } else if (e.key === 'Tab') {
      if (isOpen) updateIsOpen(false);
    }
  };

  const isCentered = align === 'center';

  return (
    <div
      ref={containerRef}
      className={`sov-select-container ${isOpen ? 'is-open' : ''} ${disabled ? 'is-disabled' : ''} ${className}`}
      style={{
        ...style,
        position: 'relative',
        zIndex: isOpen ? 1000 : (style?.zIndex || undefined),
      }}
    >
      <button
        type="button"
        id={id}
        className={`sov-select-trigger ${isCentered ? 'align-center' : ''}`}
        onClick={handleToggle}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-label={ariaLabel || placeholder}
      >
        <span className="sov-select-value">
          {selectedOption ? selectedOption.label : placeholder}
        </span>
        <svg
          className="sov-select-chevron"
          viewBox="0 0 24 24"
          width="15"
          height="15"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {isOpen && (
        <div className={`sov-select-popover ${isCentered ? 'align-center' : ''}`} role="listbox" ref={listRef}>
          <div className="sov-select-list">
            {normalizedOptions.length === 0 ? (
              <div className="sov-select-empty">No options available</div>
            ) : (
              normalizedOptions.map((opt, idx) => {
                const isSelected = opt.value === String(value);
                const isHighlighted = idx === highlightIndex;
                return (
                  <div
                    key={opt.value}
                    role="option"
                    aria-selected={isSelected}
                    aria-disabled={opt.disabled}
                    className={`sov-select-item ${isSelected ? 'is-selected' : ''} ${
                      isHighlighted ? 'is-highlighted' : ''
                    } ${opt.disabled ? 'is-disabled' : ''} ${isCentered ? 'text-center' : ''}`}
                    onClick={() => {
                      if (!opt.disabled) handleSelect(opt.value);
                    }}
                    onMouseEnter={() => setHighlightIndex(idx)}
                  >
                    <span className="sov-select-item-label">{opt.label}</span>
                    {isSelected && (
                      <svg
                        className="sov-select-check"
                        viewBox="0 0 24 24"
                        width="14"
                        height="14"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        aria-hidden="true"
                      >
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
}
