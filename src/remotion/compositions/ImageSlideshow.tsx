/**
 * ImageSlideshow — Remotion 截图幻灯片组件
 *
 * 展示 HTML 截图 + TTS 音频 + 转场动画
 */

import React from 'react';
import {
  AbsoluteFill,
  Sequence,
  Audio,
  Img,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
} from 'remotion';
import { TransitionSeries, linearTiming } from '@remotion/transitions';
import { fade } from '@remotion/transitions/fade';

interface SlideData {
  imageUrl: string;
  audioUrl?: string;
  duration: number; // seconds
}

export interface ImageSlideshowProps {
  slides: SlideData[];
}

export default function ImageSlideshow({ slides }: ImageSlideshowProps) {
  const { fps } = useVideoConfig();

  if (!slides.length) {
    return <AbsoluteFill style={{ backgroundColor: '#000' }} />;
  }

  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      <TransitionSeries>
        {slides.map((slide, idx) => {
          const dur = Math.max(Math.round(slide.duration * fps), fps * 3);
          return (
            <React.Fragment key={idx}>
              <TransitionSeries.Sequence durationInFrames={dur}>
                <AbsoluteFill>
                  {/* 截图 */}
                  <Img
                    src={slide.imageUrl}
                    style={{
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover',
                    }}
                  />
                  {/* 音频 */}
                  {slide.audioUrl && (
                    <Audio src={slide.audioUrl} volume={1} />
                  )}
                </AbsoluteFill>
              </TransitionSeries.Sequence>
              {idx < slides.length - 1 && (
                <TransitionSeries.Transition
                  timing={linearTiming({ durationInFrames: Math.round(0.5 * fps) })}
                  presentation={fade()}
                />
              )}
            </React.Fragment>
          );
        })}
      </TransitionSeries>
    </AbsoluteFill>
  );
}
