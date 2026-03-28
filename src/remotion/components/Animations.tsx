/**
 * Remotion Ken Burns Animation Engine
 * Makes static PNG slides feel dynamic
 */

import React from 'react';
import { interpolate, useCurrentFrame, useVideoConfig } from 'remotion';

/** Slow zoom in - for big numbers, quotes, covers */
export const ZoomIn: React.FC<{ children: React.ReactNode; speed?: number }> = ({ children, speed = 0.05 }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const scale = interpolate(frame, [0, durationInFrames], [1, 1 + speed], {
    extrapolateRight: 'clamp',
  });
  return (
    <div style={{ width: '100%', height: '100%', transform: `scale(${scale})`, transformOrigin: 'center' }}>
      {children}
    </div>
  );
};

/** Slow pan left - for full background image pages */
export const PanLeft: React.FC<{ children: React.ReactNode; distance?: number }> = ({ children, distance = 20 }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const translateX = interpolate(frame, [0, durationInFrames], [0, -distance], {
    extrapolateRight: 'clamp',
  });
  return (
    <div style={{ width: '100%', height: '100%', transform: `translateX(${translateX}px)` }}>
      {children}
    </div>
  );
};

/** Slow pan right */
export const PanRight: React.FC<{ children: React.ReactNode; distance?: number }> = ({ children, distance = 20 }) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const translateX = interpolate(frame, [0, durationInFrames], [0, distance], {
    extrapolateRight: 'clamp',
  });
  return (
    <div style={{ width: '100%', height: '100%', transform: `translateX(${translateX}px)` }}>
      {children}
    </div>
  );
};

/** Static (no animation) */
export const Static: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ width: '100%', height: '100%' }}>{children}</div>
);

/** Route action intent to animation wrapper */
export function getMotionWrapper(action: string, children: React.ReactNode): React.ReactNode {
  switch (action) {
    case 'zoom_in': return <ZoomIn>{children}</ZoomIn>;
    case 'pan_left': return <PanLeft>{children}</PanLeft>;
    case 'pan_right': return <PanRight>{children}</PanRight>;
    default: return <Static>{children}</Static>;
  }
}
